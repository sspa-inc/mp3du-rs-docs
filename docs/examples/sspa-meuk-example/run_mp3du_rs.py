"""
Run mp3du-rs (Rust) SSP&A particle tracking on Example 5a — MEUK Equivalent.

This script validates the Rust SSP&A (kriging-based) velocity engine against
the legacy C++ MEUK outputs.  It uses the same model inputs as the C++ run:

  - 201×201 structured grid (100 m cells), single layer.
  - Hydraulic conductivity = 100 m/d (constant).
  - Porosity = 0.3 (constant).
  - Kriged heads from an ASC raster (reversed row order to match C++).
  - Three extraction wells read from MEUK_WELLS.csv.
  - 144 particles from PartStart_Intersect.shp, repeated N times.
  - Three endpoint simulations at 5044, 23363, and 50000 days.

Validation compares Rust endpoint concentrations against C++ reference
shapefiles (MEUK_05044.shp, MEUK_23363.shp, MEUK_50000.shp) using Pearson
correlation, normalized RMSE, and captured-mass error.

Input files (all in this directory):
  mp3du.gsf                  Grid geometry (mod-PATH3DU v1.1.0 GSF format)
  Heads_for_MEUK.asc         Kriged steady-state heads (201×201)
  MEUK_WELLS.csv             Three extraction wells (NAME, X, Y, TERM, EVENT, VAL)
  PartStart_Intersect.shp    144 particle starting locations

Reference files (in ../Shapefiles/):
  MEUK_05044.shp             C++ concentration grid at t=5044 d
  MEUK_23363.shp             C++ concentration grid at t=23363 d
  MEUK_50000.shp             C++ concentration grid at t=50000 d

Requirements:
  Python packages: numpy, pyshp (shapefile), matplotlib
  Native package:  mp3du (built via ``maturin develop --release``)
"""
import csv
import json
import os
import sys
import time

import numpy as np
import shapefile
import mp3du

# ── Configuration ─────────────────────────────────────────────────────
MODEL_WS = os.path.dirname(os.path.abspath(__file__))
SHAPEFILE_DIR = os.path.join(os.path.dirname(MODEL_WS), "Shapefiles")

# Grid constants (from Ex4_MEUK.json / gsf.json)
NCOLS = 201
NROWS = 201
CELLSIZE = 100.0
XLLCORNER = 0.0
YLLCORNER = 0.0

# Model constants
HHK = 100.0          # hydraulic conductivity (m/d)
POROSITY = 0.3        # effective porosity
RETARDATION = 1.0
SEARCH_RADIUS = 300.0 # kriging neighbourhood radius (m)
KRIG_OFFSET = 0.1     # finite-difference offset for kriging velocity

# Dispersion parameters (from Ex4_MEUK.json)
DISP_LONGITUDINAL = 100.0      # m
DISP_TRANSVERSE_H = 10.0       # m

# Simulation configurations (from Ex4_MEUK.json)
SIMULATIONS = [
    {"name": "day05044_v2", "end_time": 5044.0, "ref_shp": "MEUK_05044"},
    {"name": "day23363_v2", "end_time": 23363.0, "ref_shp": "MEUK_23363"},
    {"name": "day50000_v2", "end_time": 50000.0, "ref_shp": "MEUK_50000"},
]

CAPTURE_RADIUS = 150.0   # well capture radius (m) — matches C++
INITIAL_DT = 0.1         # days
ADAPTIVE_TOL = 1.0e-6

# Number of repeat realizations.  Start small (100) for fast validation;
# scale to 5000 to match the full C++ run.
N_REPEATS = int(os.environ.get("MP3DU_REPEATS", "100"))


# ──────────────────────────────────────────────────────────────────────
# 1. Parse the GSF file (grid geometry)
# ──────────────────────────────────────────────────────────────────────

def parse_gsf(path):
    """Parse a mod-PATH3DU v1.1.0 GSF file.

    Returns
    -------
    vertices_xy : dict[int, (float, float)]
        Vertex ID -> (x, y)
    cells : list[dict]
        Each dict: id, cx, cy, nvert, vert_ids, neighbor_ids
    """
    with open(path) as f:
        lines = f.readlines()

    _version = lines[0].strip()
    n_verts = int(lines[1].strip())

    vertices_xy = {}
    for i in range(2, 2 + n_verts):
        parts = lines[i].split()
        vid = int(parts[0])
        vx, vy = float(parts[1]), float(parts[2])
        vertices_xy[vid] = (vx, vy)

    cells = []
    for i in range(2 + n_verts, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        parts = line.split()
        cell_id = int(parts[0])
        cx, cy = float(parts[1]), float(parts[2])
        nv = int(parts[3])
        vert_ids = [int(parts[4 + j]) for j in range(nv)]
        neighbor_ids = [int(parts[4 + nv + j]) for j in range(nv)]
        cells.append({
            "id": cell_id,
            "cx": cx,
            "cy": cy,
            "nvert": nv,
            "vert_ids": vert_ids,
            "neighbor_ids": neighbor_ids,
        })

    return vertices_xy, cells


# ──────────────────────────────────────────────────────────────────────
# 2. Read and reverse the ASC heads raster
#
# The ASC format stores rows top-to-bottom (north to south).
# The C++ loader reads rows in reverse: for(i=nrow-1; i>=0; i--)
# so row 0 in the resulting array corresponds to the BOTTOM of the grid.
# We replicate this with np.flipud().
# ──────────────────────────────────────────────────────────────────────

def read_asc(path):
    """Read an ASC raster and reverse row order to match C++ semantics.

    Returns
    -------
    data : np.ndarray, shape (nrows, ncols)
        Row 0 = bottom (south), row nrows-1 = top (north).
    header : dict
        ncols, nrows, xllcorner, yllcorner, cellsize, nodata_value
    """
    header = {}
    header_lines = 0
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[0].upper() in (
                "NCOLS", "NROWS", "XLLCORNER", "YLLCORNER",
                "CELLSIZE", "NODATA_VALUE",
            ):
                key = parts[0].lower()
                header[key] = float(parts[1]) if "." in parts[1] else int(parts[1])
                header_lines += 1
            else:
                break

    # ASC files may have varying numbers of values per line (not a fixed
    # rectangular text table), so we read all tokens and reshape.
    with open(path) as fh:
        for _ in range(header_lines):
            fh.readline()
        tokens = fh.read().split()
    nrows = int(header.get("nrows", NROWS))
    ncols = int(header.get("ncols", NCOLS))
    data = np.array(tokens, dtype=np.float64).reshape(nrows, ncols)

    # Reverse row order: C++ reads bottom-to-top
    data = np.flipud(data)

    return data, header


# ──────────────────────────────────────────────────────────────────────
# 3. Parse well drift data from CSV
# ──────────────────────────────────────────────────────────────────────

def read_wells_csv(path):
    """Read MEUK_WELLS.csv and return drift dictionaries for fit_sspa.

    Returns
    -------
    drifts : list[dict]
        Each dict has keys: type, event, term, name, value, x, y
    """
    drifts = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
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


# ──────────────────────────────────────────────────────────────────────
# 4. Load reference concentrations from C++ shapefile
# ──────────────────────────────────────────────────────────────────────

def load_reference_concentration(shp_basename):
    """Load reference concentration grid from a MEUK_*.shp file.

    Returns
    -------
    conc : np.ndarray, shape (nrows * ncols,)
        Concentration per cell in row-major order (row 1 col 1 first).
    """
    sf = shapefile.Reader(shp_basename)
    n = len(sf)
    conc = np.zeros(n, dtype=np.float64)
    for i, rec in enumerate(sf.iterRecords()):
        conc[i] = rec["concentrat"]
    return conc


# ──────────────────────────────────────────────────────────────────────
# 5. Build cell-to-grid mapping for endpoint binning
#
# The GSF cells are ordered row-major for a structured grid, but we
# use the cell centroid coordinates to map cell IDs to (row, col) in
# the 201×201 grid.  This uses grid lookup semantics rather than direct
# row/column arithmetic from endpoint coordinates.
# ──────────────────────────────────────────────────────────────────────

def build_cell_to_rc(gsf_cells):
    """Map each GSF cell index (0-based) to (row, col) in the grid.

    Uses the grid coordinate system:
      col = floor((cx - xll) / cellsize)
      row = floor((cy - yll) / cellsize)

    where (cx, cy) is the cell centroid from the GSF.  This keeps the
    mapping consistent with the grid's spatial index.

    Returns
    -------
    cell_row : np.ndarray of int, shape (n_cells,)
    cell_col : np.ndarray of int, shape (n_cells,)
    """
    n = len(gsf_cells)
    cell_row = np.zeros(n, dtype=np.int32)
    cell_col = np.zeros(n, dtype=np.int32)
    for ci, cell in enumerate(gsf_cells):
        cx, cy = cell["cx"], cell["cy"]
        c = int((cx - XLLCORNER) / CELLSIZE)
        r = int((cy - YLLCORNER) / CELLSIZE)
        cell_col[ci] = min(c, NCOLS - 1)
        cell_row[ci] = min(r, NROWS - 1)
    return cell_row, cell_col


# ──────────────────────────────────────────────────────────────────────
# 6. Bin endpoints into a concentration grid using cell IDs
#
# The tracker reports the cell_id each particle ends in. We use the
# GSF cell→(row,col) mapping (grid lookup semantics) to bin endpoints
# into a 201×201 concentration grid, rather than computing row/col
# from the endpoint (x, y) coordinates directly.
# ──────────────────────────────────────────────────────────────────────

def bin_endpoints(results, cell_row, cell_col, n_cells):
    """Bin simulation endpoints into a per-cell concentration array.

    Uses the cell_id from the last trajectory record (the endpoint)
    and maps it to a grid cell via the pre-built cell→(row,col) table.

    Parameters
    ----------
    results : list of TrajectoryResult
    cell_row, cell_col : arrays from build_cell_to_rc
    n_cells : total number of cells

    Returns
    -------
    conc : np.ndarray, shape (n_cells,)
        Count of endpoints per cell.
    """
    conc = np.zeros(n_cells, dtype=np.float64)
    for r in results:
        records = r.to_records()
        if not records:
            continue
        last = records[-1]
        cid = last["cell_id"]
        if 0 <= cid < n_cells:
            conc[cid] += 1.0
    return conc


# ──────────────────────────────────────────────────────────────────────
# 7. Validation metrics
# ──────────────────────────────────────────────────────────────────────

def compute_metrics(rust_conc, ref_conc):
    """Compute comparison metrics between two concentration arrays.

    Returns
    -------
    dict with keys:
        pearson_r       – Pearson correlation coefficient
        nrmse           – Normalized RMSE (relative to reference range)
        mass_error_pct  – Captured-mass error as a percentage
        rust_total      – Total concentration (Rust)
        ref_total       – Total concentration (reference)
    """
    metrics = {}

    ref_total = ref_conc.sum()
    rust_total = rust_conc.sum()
    metrics["ref_total"] = ref_total
    metrics["rust_total"] = rust_total

    if ref_total > 0:
        metrics["mass_error_pct"] = 100.0 * (rust_total - ref_total) / ref_total
    else:
        metrics["mass_error_pct"] = 0.0

    # Pearson correlation
    mask = (ref_conc > 0) | (rust_conc > 0)
    if mask.sum() > 1:
        r_ref = ref_conc[mask]
        r_rust = rust_conc[mask]
        if r_ref.std() > 0 and r_rust.std() > 0:
            metrics["pearson_r"] = float(np.corrcoef(r_ref, r_rust)[0, 1])
        else:
            metrics["pearson_r"] = float("nan")
    else:
        metrics["pearson_r"] = float("nan")

    # Normalized RMSE
    ref_range = ref_conc.max() - ref_conc.min()
    rmse = np.sqrt(np.mean((rust_conc - ref_conc) ** 2))
    if ref_range > 0:
        metrics["nrmse"] = float(rmse / ref_range)
    else:
        metrics["nrmse"] = float(rmse)

    return metrics


# ══════════════════════════════════════════════════════════════════════
#  PLOTS
# ══════════════════════════════════════════════════════════════════════

def _save_head_plot(heads_2d, base_particles, drifts, all_trajectories, simulations, out_dir):
    """Head-contour + particle-path overlay for each simulation.

    Only the first repeat's trajectories are plotted so the figure stays
    readable when N_REPEATS is large.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patheffects as pe
    except ImportError:
        print("matplotlib not available — skipping head-contour plot")
        return

    n_sims = len(simulations)
    fig, axes = plt.subplots(1, n_sims, figsize=(7 * n_sims, 7), constrained_layout=True)
    if n_sims == 1:
        axes = [axes]

    x_centres = XLLCORNER + (np.arange(NCOLS) + 0.5) * CELLSIZE
    y_centres = YLLCORNER + (np.arange(NROWS) + 0.5) * CELLSIZE
    X, Y = np.meshgrid(x_centres, y_centres)

    h_min, h_max = heads_2d.min(), heads_2d.max()
    levels_fill = np.linspace(h_min, h_max, 40)
    levels_line = np.linspace(h_min, h_max, 12)

    starts_x = [bp["x"] for bp in base_particles]
    starts_y = [bp["y"] for bp in base_particles]
    well_x   = [d["x"]  for d in drifts]
    well_y   = [d["y"]  for d in drifts]
    well_names = [d["name"] for d in drifts]

    sim_colors = ["steelblue", "darkorange", "crimson"]

    for ax, sim, color in zip(axes, simulations, sim_colors):
        name     = sim["name"]
        end_time = sim["end_time"]

        cf = ax.contourf(X, Y, heads_2d, levels=levels_fill, cmap="Blues_r", alpha=0.7)
        cs = ax.contour(X, Y, heads_2d, levels=levels_line, colors="k",
                        linewidths=0.4, alpha=0.5)
        ax.clabel(cs, fmt="%.1f", fontsize=6, inline=True)
        fig.colorbar(cf, ax=ax, label="Head (m)", shrink=0.8)

        for path in all_trajectories.get(name, []):
            if not path:
                continue
            xs = [pt[0] for pt in path]
            ys = [pt[1] for pt in path]
            ax.plot(xs, ys, color=color, lw=0.6, alpha=0.5)
            mid = len(path) // 2
            if len(path) >= 2:
                ax.annotate("", xy=path[mid], xytext=path[max(mid - 1, 0)],
                            arrowprops=dict(arrowstyle="->", color=color, lw=0.8))

        ax.scatter(starts_x, starts_y, s=6, c="lime", zorder=5,
                   label="Particle start", edgecolors="k", linewidths=0.3)
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

    fig.suptitle(f"Example 5a — MEUK SSP&A with dispersion  (1 of {N_REPEATS} repeats)",
                 fontsize=12)
    out_path = os.path.join(out_dir, "run_mp3du_rs_head_plot.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Head-contour plot saved: {out_path}")


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print(f"mp3du-rs version: {mp3du.version()}")
    print(f"Repeat count: {N_REPEATS}  (set MP3DU_REPEATS=5000 for full run)")
    print()

    # ── 1. Parse GSF ──────────────────────────────────────────────────
    gsf_path = os.path.join(MODEL_WS, "mp3du.gsf")
    print("Parsing GSF file...")
    vertices_xy, gsf_cells = parse_gsf(gsf_path)
    n_cells = len(gsf_cells)
    print(f"  {len(vertices_xy)} vertices, {n_cells} cells")

    # ── 2. Build mp3du grid ───────────────────────────────────────────
    print("Building grid...")
    cell_vertices_list = []
    cell_centers_list = []

    for cell in gsf_cells:
        verts = [
            (vertices_xy[vid][0], vertices_xy[vid][1])
            for vid in cell["vert_ids"]
        ]
        cell_vertices_list.append(verts)
        # z-center is arbitrary for the 2-D MEUK model; use 0.
        cell_centers_list.append((cell["cx"], cell["cy"], 0.0))

    grid = mp3du.build_grid(cell_vertices_list, cell_centers_list)
    print(f"  Grid built: {grid.n_cells()} cells")

    # ── 3. Read ASC heads (reversed row order) ────────────────────────
    asc_path = os.path.join(MODEL_WS, "Heads_for_MEUK.asc")
    print("Reading ASC heads (with row reversal)...")
    heads_2d, _hdr = read_asc(asc_path)
    print(f"  Shape: {heads_2d.shape}  Range: [{heads_2d.min():.4f}, {heads_2d.max():.4f}]")

    # Flatten heads to 1-D in row-major order matching GSF cell ordering.
    # After flipud, row 0 is the bottom row of the grid.
    # GSF cell ordering: cell 0 is at (cx=50, cy=50) which is row 0 col 0
    # (bottom-left of the grid). This matches the flipped ASC layout.
    heads_flat = heads_2d.flatten()
    assert heads_flat.shape[0] == n_cells, (
        f"Heads count {heads_flat.shape[0]} != GSF cells {n_cells}"
    )

    # ── 4. Read well drifts ───────────────────────────────────────────
    wells_path = os.path.join(MODEL_WS, "MEUK_WELLS.csv")
    print("Reading well drifts...")
    drifts = read_wells_csv(wells_path)
    for d in drifts:
        print(f"  {d['name']}: ({d['x']}, {d['y']}), Q={d['value']}, "
              f"event={d['event']}, term={d['term']}")

    # ── 5. Build well mask ────────────────────────────────────────────
    # Mark cells that contain a well so kriging excludes them.
    well_mask = np.zeros(n_cells, dtype=np.bool_)
    for d in drifts:
        # Find the cell whose centroid is closest to the well
        wx, wy = d["x"], d["y"]
        col = int((wx - XLLCORNER) / CELLSIZE)
        row = int((wy - YLLCORNER) / CELLSIZE)
        col = min(max(col, 0), NCOLS - 1)
        row = min(max(row, 0), NROWS - 1)
        idx = row * NCOLS + col
        if 0 <= idx < n_cells:
            well_mask[idx] = True
            print(f"  Well mask set at cell {idx} (row={row}, col={col})")

    # ── 6. Hydrate SSP&A inputs and fit the field ─────────────────────
    print("Hydrating SSP&A inputs...")
    sspa_inputs = mp3du.hydrate_sspa_inputs(
        heads=heads_flat,
        porosity=np.full(n_cells, POROSITY, dtype=np.float64),
        well_mask=well_mask,
        hhk=np.full(n_cells, HHK, dtype=np.float64),
    )

    print("Fitting SSP&A velocity field...")
    sspa_cfg = mp3du.SspaConfig(
        search_radius=SEARCH_RADIUS,
        krig_offset=KRIG_OFFSET,
    )
    t0 = time.perf_counter()
    field = mp3du.fit_sspa(sspa_cfg, grid, sspa_inputs, drifts)
    dt_fit = time.perf_counter() - t0
    print(f"  Field fitted: {field.method_name()}, {field.n_cells()} cells  ({dt_fit:.2f} s)")

    # ── 7. Load particle starting positions ───────────────────────────
    shp_path = os.path.join(MODEL_WS, "PartStart_Intersect")
    print("Loading particle start locations...")
    sf = shapefile.Reader(shp_path)
    base_particles = []
    for i, sr in enumerate(sf.iterShapeRecords()):
        attrs = sr.record.as_dict()
        pt = sr.shape.points[0]
        cell_id_1based = attrs["P3D_CellID"]
        cell_id = cell_id_1based - 1  # 0-based
        zloc = attrs.get("ZLOC", 0.5) or 0.5
        base_particles.append({
            "x": pt[0],
            "y": pt[1],
            "z": zloc,
            "cell_id": cell_id,
        })
    print(f"  {len(base_particles)} base particles loaded")

    # ── 8. Build cell→(row,col) mapping for endpoint binning ─────────
    cell_row, cell_col = build_cell_to_rc(gsf_cells)

    # ── 9. Run simulations ────────────────────────────────────────────
    # Build particles with REPEAT realizations (each base particle is
    # replicated N_REPEATS times with unique IDs).
    all_metrics = {}
    all_results = {}           # sim_name -> list[TrajectoryResult]
    all_trajectories = {}      # sim_name -> list of [(x,y),...] for first repeat

    for sim in SIMULATIONS:
        sim_name = sim["name"]
        end_time = sim["end_time"]
        ref_shp = sim["ref_shp"]
        print(f"\n{'='*60}")
        print(f"Simulation: {sim_name}  (t_end = {end_time} d, repeats = {N_REPEATS})")
        print(f"{'='*60}")

        # Build simulation config
        config_dict = {
            "velocity_method": "Waterloo",
            "solver": "DormandPrince",
            "adaptive": {
                "tolerance": ADAPTIVE_TOL,
                "safety": 0.9,
                "alpha": 0.2,
                "min_scale": 0.2,
                "max_scale": 5.0,
                "max_rejects": 10,
                "min_dt": 1e-10,
                "euler_dt": 1e-20,
            },
            "dispersion": {
                "method": "Ito",
                "alpha_l": DISP_LONGITUDINAL,
                "alpha_th": DISP_TRANSVERSE_H,
                "alpha_tv": 0.0,
            },
            "retardation_enabled": RETARDATION != 1.0,
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
        }
        config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))

        # Build repeated particle list
        particles = []
        pid = 0
        for _rep in range(N_REPEATS):
            for bp in base_particles:
                particles.append(mp3du.ParticleStart(
                    id=pid,
                    x=bp["x"],
                    y=bp["y"],
                    z=bp["z"],
                    cell_id=bp["cell_id"],
                    initial_dt=INITIAL_DT,
                ))
                pid += 1

        total_particles = len(particles)
        print(f"  Total particles: {total_particles} "
              f"({len(base_particles)} base × {N_REPEATS} repeats)")

        # Run
        t0 = time.perf_counter()
        results = mp3du.run_simulation(config, field, particles, parallel=True)
        dt_sim = time.perf_counter() - t0
        print(f"  Simulation complete: {len(results)} trajectories  ({dt_sim:.1f} s)")
        all_results[sim_name] = results

        # Collect particle paths for first repeat only (for head-contour plot)
        n_base = len(base_particles)
        paths = []
        for r in results[:n_base]:
            recs = r.to_records()
            if recs:
                paths.append([(rec["x"], rec["y"]) for rec in recs])
        all_trajectories[sim_name] = paths

        # Summarise termination statuses
        status_counts = {}
        for r in results:
            status_counts[r.final_status] = status_counts.get(r.final_status, 0) + 1
        for status, count in sorted(status_counts.items()):
            print(f"    {status}: {count}")

        # Bin endpoints into concentration grid
        rust_conc = bin_endpoints(results, cell_row, cell_col, n_cells)
        print(f"  Non-zero cells (Rust): {(rust_conc > 0).sum()}")

        # Load reference
        ref_path = os.path.join(SHAPEFILE_DIR, ref_shp)
        if os.path.exists(ref_path + ".shp"):
            print(f"  Loading reference: {ref_shp}.shp")
            ref_conc = load_reference_concentration(ref_path)

            # The reference shapefile stores cells in row-major order with
            # row 1 = top of grid.  The GSF cell-index ordering has row 0 =
            # bottom.  We need to remap the reference to match GSF order.
            # Reference: row i, col j -> flat index (i-1)*ncols + (j-1)
            # where row 1 is the TOP (north).  GSF: row 0 is BOTTOM (south).
            # So reference row r (1-based top) maps to GSF row (nrows - r).
            ref_reordered = np.zeros(n_cells, dtype=np.float64)
            for i in range(NROWS):
                for j in range(NCOLS):
                    # Reference flat index: row i (0-based from top), col j
                    ref_idx = i * NCOLS + j
                    # GSF row = (NROWS - 1 - i), col = j  -> GSF flat index
                    gsf_idx = (NROWS - 1 - i) * NCOLS + j
                    ref_reordered[gsf_idx] = ref_conc[ref_idx]

            # Scale Rust concentration to match reference particle count
            # (reference used 5000 repeats × 144 particles)
            if N_REPEATS != 5000:
                scale = 5000.0 / N_REPEATS
                rust_conc_scaled = rust_conc * scale
                print(f"  Scaling Rust concentrations by {scale:.1f}x "
                      f"(normalising {N_REPEATS} -> 5000 repeats)")
            else:
                rust_conc_scaled = rust_conc

            metrics = compute_metrics(rust_conc_scaled, ref_reordered)
            all_metrics[sim_name] = metrics

            print(f"\n  Validation metrics vs C++ reference:")
            print(f"    Pearson r:      {metrics['pearson_r']:.4f}")
            print(f"    Norm. RMSE:     {metrics['nrmse']:.4f}")
            print(f"    Mass error:     {metrics['mass_error_pct']:+.2f}%")
            print(f"    Total (Rust):   {metrics['rust_total']:.1f}")
            print(f"    Total (C++):    {metrics['ref_total']:.1f}")
        else:
            print(f"  WARNING: Reference shapefile not found: {ref_path}.shp")
            print(f"           Skipping validation for {sim_name}")

    # ── 10. Summary ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Repeats: {N_REPEATS}  (set MP3DU_REPEATS=5000 for full run)")
    for name, m in all_metrics.items():
        print(f"  {name}:  r={m['pearson_r']:.4f}  nRMSE={m['nrmse']:.4f}  "
              f"mass_err={m['mass_error_pct']:+.2f}%")

    # ── 11. Head-contour + particle-path overlay plot ─────────────────
    _save_head_plot(heads_2d, base_particles, drifts, all_trajectories, SIMULATIONS, MODEL_WS)

    # ── 12. Optional: reference comparison plots ─────────────────────
    try:
        import matplotlib.pyplot as plt

        for sim in SIMULATIONS:
            sim_name = sim["name"]
            ref_shp = sim["ref_shp"]
            ref_path = os.path.join(SHAPEFILE_DIR, ref_shp)
            if not os.path.exists(ref_path + ".shp"):
                continue
            if sim_name not in all_metrics:
                continue

            ref_conc = load_reference_concentration(ref_path)
            # Reorder reference to GSF order
            ref_grid = np.zeros((NROWS, NCOLS), dtype=np.float64)
            for i in range(NROWS):
                for j in range(NCOLS):
                    ref_idx = i * NCOLS + j
                    ref_grid[NROWS - 1 - i, j] = ref_conc[ref_idx]

            # Re-derive the 2-D concentration grids for plotting
            rust_flat = bin_endpoints(all_results[sim_name], cell_row, cell_col, n_cells)
            if N_REPEATS != 5000:
                rust_flat = rust_flat * (5000.0 / N_REPEATS)
            rust_grid = rust_flat.reshape(NROWS, NCOLS)

            fig, axes = plt.subplots(1, 3, figsize=(18, 5))
            extent = [XLLCORNER, XLLCORNER + NCOLS * CELLSIZE,
                      YLLCORNER, YLLCORNER + NROWS * CELLSIZE]

            vmax = max(ref_grid.max(), rust_grid.max(), 1.0)

            axes[0].imshow(ref_grid, origin="lower", extent=extent,
                           vmin=0, vmax=vmax, cmap="hot_r")
            axes[0].set_title(f"C++ Reference ({ref_shp})")

            axes[1].imshow(rust_grid, origin="lower", extent=extent,
                           vmin=0, vmax=vmax, cmap="hot_r")
            axes[1].set_title(f"Rust SSP&A (×{N_REPEATS})")

            diff = rust_grid - ref_grid
            dmax = max(abs(diff.min()), abs(diff.max()), 1.0)
            im = axes[2].imshow(diff, origin="lower", extent=extent,
                                vmin=-dmax, vmax=dmax, cmap="RdBu_r")
            axes[2].set_title("Difference (Rust − C++)")
            fig.colorbar(im, ax=axes[2], shrink=0.8)

            for ax in axes:
                ax.set_xlabel("X (m)")
                ax.set_ylabel("Y (m)")

            fig.suptitle(f"Example 5a — {sim_name}  "
                         f"(r={all_metrics[sim_name]['pearson_r']:.3f})")
            fig.tight_layout()
            plot_path = os.path.join(MODEL_WS, f"validation_{sim_name}.png")
            fig.savefig(plot_path, dpi=150)
            plt.close(fig)
            print(f"  Plot saved: {plot_path}")

    except ImportError:
        print("  matplotlib not available — skipping plots")

    print("\nDone.")


if __name__ == "__main__":
    main()
