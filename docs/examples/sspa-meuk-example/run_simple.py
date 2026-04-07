"""
Minimal smoke test: one particle per release location, no repeats, no dispersion.
Three endpoint times: 5044, 23363, 50000 days.
Prints termination status for every particle and saves a validation plot.

NOTE on fit_sspa performance (353 s for 201x201 grid)
------------------------------------------------------
`fit_sspa` calls `SspaField::new()` which calls `build_neighborhood()` for
every cell via `grid.query_bbox()`.  `query_bbox` is a *stub linear scan*
over all 40,401 cells (an R-tree acceleration is noted as a future task in
mp3du-grid/src/grid.rs).  That makes the precomputation O(n^2) ≈ 1.6 billion
bbox checks.  The actual kriging LDL decompositions are *lazy* (only computed
on the first `velocity_at()` call for each cell), so particles only pay for
cells they visit.  Fix: replace the linear scan with a 2-D grid-hash or
R-tree in `build_neighborhood()` in Rust — O(n²) → O(n·k).
"""
import csv
import json
import os
import time

import numpy as np
import shapefile
import mp3du

MODEL_WS = os.path.dirname(os.path.abspath(__file__))

NCOLS = 201
NROWS = 201
CELLSIZE = 100.0
XLLCORNER = 0.0
YLLCORNER = 0.0

HHK = 100.0
POROSITY = 0.3
SEARCH_RADIUS = 300.0
KRIG_OFFSET = 0.1
CAPTURE_RADIUS = 150.0
INITIAL_DT = 0.1

SIMULATIONS = [
    {"name": "day05044", "end_time": 5044.0},
    {"name": "day23363", "end_time": 23363.0},
    {"name": "day50000", "end_time": 50000.0},
]


# ── helpers ──────────────────────────────────────────────────────────

def parse_gsf(path):
    with open(path) as f:
        lines = f.readlines()
    n_verts = int(lines[1].strip())
    vertices_xy = {}
    for i in range(2, 2 + n_verts):
        parts = lines[i].split()
        vertices_xy[int(parts[0])] = (float(parts[1]), float(parts[2]))
    cells = []
    for i in range(2 + n_verts, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        parts = line.split()
        nv = int(parts[3])
        cells.append({
            "id": int(parts[0]),
            "cx": float(parts[1]),
            "cy": float(parts[2]),
            "nvert": nv,
            "vert_ids": [int(parts[4 + j]) for j in range(nv)],
            "neighbor_ids": [int(parts[4 + nv + j]) for j in range(nv)],
        })
    return vertices_xy, cells


def read_asc(path):
    header = {}
    header_lines = 0
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[0].upper() in (
                "NCOLS", "NROWS", "XLLCORNER", "YLLCORNER", "CELLSIZE", "NODATA_VALUE"
            ):
                header[parts[0].lower()] = (
                    float(parts[1]) if "." in parts[1] else int(parts[1])
                )
                header_lines += 1
            else:
                break
    with open(path) as fh:
        for _ in range(header_lines):
            fh.readline()
        tokens = fh.read().split()
    nrows = int(header.get("nrows", NROWS))
    ncols = int(header.get("ncols", NCOLS))
    data = np.array(tokens, dtype=np.float64).reshape(nrows, ncols)
    return np.flipud(data)


def read_wells_csv(path):
    drifts = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            drifts.append({
                "type": "well",
                "event": row["EVENT"].strip(),
                "term": int(row["TERM"]),
                "name": row["NAME"].strip(),
                "value": float(row["VAL"]),
                "x": float(row["XCOORDS"]),
                "y": float(row["YCOORDS"]),
            })
    return drifts


# ── main ─────────────────────────────────────────────────────────────

def main():
    print(f"mp3du version: {mp3du.version()}")

    # 1. GSF
    print("\nParsing GSF...")
    vertices_xy, gsf_cells = parse_gsf(os.path.join(MODEL_WS, "mp3du.gsf"))
    n_cells = len(gsf_cells)
    print(f"  {len(vertices_xy)} vertices, {n_cells} cells")

    # 2. Build grid
    print("Building grid...")
    cell_vertices_list = [
        [(vertices_xy[vid][0], vertices_xy[vid][1]) for vid in c["vert_ids"]]
        for c in gsf_cells
    ]
    cell_centers_list = [(c["cx"], c["cy"], 0.0) for c in gsf_cells]
    grid = mp3du.build_grid(cell_vertices_list, cell_centers_list)
    print(f"  {grid.n_cells()} cells in grid")

    # 3. Heads
    print("Reading ASC heads...")
    heads_2d = read_asc(os.path.join(MODEL_WS, "Heads_for_MEUK.asc"))
    heads_flat = heads_2d.flatten()
    print(f"  Shape {heads_2d.shape}, range [{heads_flat.min():.4f}, {heads_flat.max():.4f}]")
    assert heads_flat.shape[0] == n_cells

    # 4. Wells
    print("Reading wells...")
    drifts = read_wells_csv(os.path.join(MODEL_WS, "MEUK_WELLS.csv"))
    for d in drifts:
        print(f"  {d['name']}: ({d['x']}, {d['y']}), Q={d['value']}")

    # 5. Well mask
    well_mask = np.zeros(n_cells, dtype=np.bool_)
    for d in drifts:
        col = min(max(int((d["x"] - XLLCORNER) / CELLSIZE), 0), NCOLS - 1)
        row = min(max(int((d["y"] - YLLCORNER) / CELLSIZE), 0), NROWS - 1)
        idx = row * NCOLS + col
        if 0 <= idx < n_cells:
            well_mask[idx] = True
            print(f"  Well mask: cell {idx} (row={row}, col={col})")

    # 6. Fit SSP&A
    print("\nHydrating SSP&A inputs...")
    sspa_inputs = mp3du.hydrate_sspa_inputs(
        heads=heads_flat,
        porosity=np.full(n_cells, POROSITY, dtype=np.float64),
        well_mask=well_mask,
        hhk=np.full(n_cells, HHK, dtype=np.float64),
    )

    print("Fitting SSP&A field...")
    t0 = time.perf_counter()
    field = mp3du.fit_sspa(
        mp3du.SspaConfig(search_radius=SEARCH_RADIUS, krig_offset=KRIG_OFFSET),
        grid,
        sspa_inputs,
        drifts,
    )
    print(f"  Fitted: {field.method_name()}, {field.n_cells()} cells  ({time.perf_counter()-t0:.1f} s)")

    # 7. Particles — one per release location, no repeats
    print("\nLoading particle starts...")
    sf = shapefile.Reader(os.path.join(MODEL_WS, "PartStart_Intersect"))
    particles = []
    for i, sr in enumerate(sf.iterShapeRecords()):
        attrs = sr.record.as_dict()
        pt = sr.shape.points[0]
        cell_id = attrs["P3D_CellID"] - 1  # 0-based
        zloc = attrs.get("ZLOC", 0.5) or 0.5
        particles.append(mp3du.ParticleStart(
            id=i,
            x=pt[0],
            y=pt[1],
            z=float(zloc),
            cell_id=cell_id,
            initial_dt=INITIAL_DT,
        ))
    print(f"  {len(particles)} particles")

    # 8. Simulations
    all_trajectories = {}   # sim_name -> list of [(x, y), ...]  per particle
    for sim in SIMULATIONS:
        name = sim["name"]
        end_time = sim["end_time"]
        print(f"\n{'='*55}")
        print(f"Simulation: {name}  end_time={end_time} d  particles={len(particles)}")
        print(f"{'='*55}")

        config = mp3du.SimulationConfig.from_json(json.dumps({
            "velocity_method": "Waterloo",
            "solver": "DormandPrince",
            "adaptive": {
                "tolerance": 1e-6,
                "safety": 0.9,
                "alpha": 0.2,
                "min_scale": 0.2,
                "max_scale": 5.0,
                "max_rejects": 10,
                "min_dt": 1e-10,
                "euler_dt": 1e-20,
            },
            "dispersion": {"method": "None"},
            "retardation_enabled": False,
            "capture": {
                "max_time": end_time,
                "max_steps": 2_000_000,
                "stagnation_velocity": 1e-12,
                "stagnation_limit": 100,
                "capture_radius": CAPTURE_RADIUS,
            },
            "initial_dt": INITIAL_DT,
            "max_dt": 1000.0,
            "direction": 1.0,
        }))

        t0 = time.perf_counter()
        results = mp3du.run_simulation(config, field, particles, parallel=True)
        elapsed = time.perf_counter() - t0
        print(f"  Done: {len(results)} trajectories  ({elapsed:.2f} s)")

        # Status summary
        status_counts: dict = {}
        for r in results:
            status_counts[r.final_status] = status_counts.get(r.final_status, 0) + 1
        for status, count in sorted(status_counts.items()):
            print(f"    {status}: {count}")

        # Collect full trajectories for plotting
        paths = []
        for r in results:
            recs = r.to_records()
            if recs:
                paths.append([(rec["x"], rec["y"]) for rec in recs])
        all_trajectories[name] = paths

        # Print endpoint location for each particle
        print(f"\n  {'ID':>4}  {'status':<22}  {'x':>10}  {'y':>10}  {'z':>7}  cell")
        print(f"  {'-'*4}  {'-'*22}  {'-'*10}  {'-'*10}  {'-'*7}  ----")
        for r in results:
            recs = r.to_records()
            if recs:
                last = recs[-1]
                print(f"  {r.particle_id:>4}  {r.final_status:<22}  "
                      f"{last['x']:>10.1f}  {last['y']:>10.1f}  "
                      f"{last.get('z', 0.0):>7.4f}  {last['cell_id']}")
            else:
                print(f"  {r.particle_id:>4}  {r.final_status:<22}  (no records)")

    # 9. Plot
    _save_plot(heads_2d, particles, drifts, all_trajectories, SIMULATIONS, MODEL_WS)

    print("\nDone.")


def _save_plot(heads_2d, particles, drifts, all_trajectories, simulations, out_dir):
    """Contour the head field and overlay particle paths for each simulation."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patheffects as pe
    except ImportError:
        print("matplotlib not available — skipping plot")
        return

    n_sims = len(simulations)
    fig, axes = plt.subplots(1, n_sims, figsize=(7 * n_sims, 7), constrained_layout=True)
    if n_sims == 1:
        axes = [axes]

    # Coordinate arrays (row 0 of heads_2d = south after flipud)
    x_centres = XLLCORNER + (np.arange(NCOLS) + 0.5) * CELLSIZE
    y_centres = YLLCORNER + (np.arange(NROWS) + 0.5) * CELLSIZE
    X, Y = np.meshgrid(x_centres, y_centres)

    # Colour map range for heads
    h_min, h_max = heads_2d.min(), heads_2d.max()
    levels_fill = np.linspace(h_min, h_max, 40)
    levels_line = np.linspace(h_min, h_max, 12)

    # Start points
    starts_x = [p.x for p in particles]
    starts_y = [p.y for p in particles]

    # Well locations
    well_x = [d["x"] for d in drifts]
    well_y = [d["y"] for d in drifts]
    well_names = [d["name"] for d in drifts]

    sim_colors = ["steelblue", "darkorange", "crimson"]

    for ax, sim, color in zip(axes, simulations, sim_colors):
        name = sim["name"]
        end_time = sim["end_time"]

        # Filled head contours
        cf = ax.contourf(X, Y, heads_2d, levels=levels_fill, cmap="Blues_r", alpha=0.7)
        cs = ax.contour(X, Y, heads_2d, levels=levels_line, colors="k",
                        linewidths=0.4, alpha=0.5)
        ax.clabel(cs, fmt="%.1f", fontsize=6, inline=True)
        fig.colorbar(cf, ax=ax, label="Head (m)", shrink=0.8)

        # Particle paths
        paths = all_trajectories.get(name, [])
        for i, path in enumerate(paths):
            if not path:
                continue
            xs = [pt[0] for pt in path]
            ys = [pt[1] for pt in path]
            ax.plot(xs, ys, color=color, lw=0.6, alpha=0.5)
            # Arrow at midpoint to show direction
            mid = len(path) // 2
            if len(path) >= 2:
                ax.annotate(
                    "",
                    xy=path[mid],
                    xytext=path[max(mid - 1, 0)],
                    arrowprops=dict(arrowstyle="->", color=color, lw=0.8),
                )

        # Particle starts
        ax.scatter(starts_x, starts_y, s=6, c="lime", zorder=5,
                   label="Particle start", edgecolors="k", linewidths=0.3)

        # Well locations
        ax.scatter(well_x, well_y, s=120, marker="v", c="red", zorder=6,
                   label="Well", edgecolors="black", linewidths=0.8)
        for wx, wy, wn in zip(well_x, well_y, well_names):
            ax.annotate(wn, (wx, wy), textcoords="offset points",
                        xytext=(5, 5), fontsize=7, color="red",
                        path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])

        ax.set_xlim(XLLCORNER, XLLCORNER + NCOLS * CELLSIZE)
        ax.set_ylim(YLLCORNER, YLLCORNER + NROWS * CELLSIZE)
        ax.set_aspect("equal")
        ax.set_title(f"{name}  (t = {end_time:,.0f} d)", fontsize=10)
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.legend(loc="upper left", fontsize=7, markerscale=1.5)

    fig.suptitle("Example 5a — MEUK SSP&A particle paths (no dispersion)", fontsize=12)

    out_path = os.path.join(out_dir, "run_simple_plot.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"\nPlot saved: {out_path}")


if __name__ == "__main__":
    main()
