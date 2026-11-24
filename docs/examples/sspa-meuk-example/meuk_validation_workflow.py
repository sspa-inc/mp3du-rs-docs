"""
Run mp3du-rs (Rust) SSP&A particle tracking on Example 5a — MEUK Equivalent.

This script validates MP3DU-RS against mod-PATH3DU 2.1.9 (C++) on the MEUK model,
with GSDE dispersion (LaBolle et al. 2000).  It uses the same model inputs as the
C++ run:

  - 201×201 structured grid (100 m cells), single layer.
  - Hydraulic conductivity = 100 m/d (constant).
  - Porosity = 0.3 (constant).
  - Kriged heads from an ASC raster (reversed row order to match C++).
  - Three extraction wells read from MEUK_WELLS.csv.
  - 144 particles from PartStart_Intersect.shp, repeated N times.
  - Three endpoint simulations at 5044, 23363, and 50000 days.

Each end time is run with two tracking set-ups (select with MP3DU_SETUPS):

  - cpp_input:  as the mod-PATH3DU input Ex4_MEUK.json (step-doubling
                Runge-Kutta, no practical step limit), like for like with the
                reference;
  - dopri_1000: Dormand-Prince with a 1,000-day step limit.

Validation converts the Rust endpoints to concentrations the way the C++
reference was made (writeUCNs.for) and compares them with the reference
concentrations in meuk_reference_concentrations.csv, made with mod-PATH3DU 2.1.9
(November 2026 build, with the GSDE fix) from Ex4_MEUK.json as published
(5,000 repeats):

  - Only particles still in the aquifer at the end time are binned.  Particles
    captured by the wells are left out, as in the C++ reference, which shows the
    mass still in the aquifer.  The number excluded per status is printed.
  - Concentration = count x mass per particle / pore volume.  Pore volume =
    head x cell area x porosity, from the MODFLOW heads.  Mass per particle =
    the mean pore volume of the 3×3 source block x 1000, divided by
    5000 repeats x 16 particles per cell.  Counts are scaled to 5000 repeats
    when N_REPEATS differs.
  - Pearson r and normalized RMSE are computed on the concentrations.
  - Mass in the aquifer = sum of concentration x pore volume over all cells.
    The mass error is (Rust - C++) / C++ of that quantity.

Input files (all in this directory):
  mp3du.gsf                  Grid geometry (mod-PATH3DU v1.1.0 GSF format)
  Heads_for_MEUK.asc         Kriged steady-state heads (201×201)
  MEUK_WELLS.csv             Three extraction wells (NAME, X, Y, TERM, EVENT, VAL)
  PartStart_Intersect.shp    144 particle starting locations

MODFLOW file (in ../01-MODFLOW/):
  dispdemoWEL.hds            MODFLOW binary heads, used for the pore volumes

Reference file (download it into this directory, next to this script):
  meuk_reference_concentrations.csv
                             mod-PATH3DU concentrations at 5044, 23363 and 50000 d

Requirements:
  Python packages: numpy, pyshp (shapefile), matplotlib
  mp3du 0.1.5 or later (pip install the wheel from the GitHub releases)
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
HEADS_FILE = os.path.join(os.path.dirname(MODEL_WS), "01-MODFLOW", "dispdemoWEL.hds")

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
    {"name": "day05044_v2", "end_time": 5044.0, "ref_column": "conc_05044"},
    {"name": "day23363_v2", "end_time": 23363.0, "ref_column": "conc_23363"},
    {"name": "day50000_v2", "end_time": 50000.0, "ref_column": "conc_50000"},
]

# Tracking set-ups. mod-PATH3DU made the reference with the defaults of
# Ex4_MEUK.json: its step-doubling Runge-Kutta and a step limit of 1e6 days.
SETUPS = {
    "cpp_input": {"label": "as the mod-PATH3DU input (step-doubling Runge-Kutta, no step limit)",
                  "solver": "Rk4StepDoubling", "max_dt": 1.0e6},
    "dopri_1000": {"label": "Dormand-Prince, 1,000-day step limit",
                   "solver": "DormandPrince", "max_dt": 1000.0},
}
SETUP_NAMES = [s for s in os.environ.get("MP3DU_SETUPS", "cpp_input,dopri_1000").split(",") if s]

# mod-PATH3DU reference concentrations, in this directory
REFERENCE_CSV = os.path.join(MODEL_WS, "meuk_reference_concentrations.csv")
REFERENCE_URL = ("https://sspa-inc.github.io/mp3du-rs-docs/examples/sspa-meuk-example/"
                 "meuk_reference_concentrations.csv")

CAPTURE_RADIUS = 150.0   # well capture radius (m) — matches C++
INITIAL_DT = 0.1         # days
ADAPTIVE_TOL = 1.0e-6

# Number of repeat realizations.  Start small (100) for fast validation;
# scale to 5000 to match the full C++ run.
N_REPEATS = int(os.environ.get("MP3DU_REPEATS", "100"))

# C++ reference concentrations (writeUCNs.for)
REF_REPEATS = 5000             # repeats per particle in the C++ run
PARTICLES_PER_CELL = 16        # particles released per source cell in the C++ run
INIT_CONC = 1000.0             # initial concentration in the source cells
SOURCE_ROWS = slice(99, 102)   # source block: rows 100-102 (1-based, from the top)
SOURCE_COLS = slice(18, 21)    #               cols 19-21 (1-based)
HEADS_HEADER_BYTES = 44        # MODFLOW heads record header before the head array

# Final statuses of particles that are still in the aquifer at the end time.
# Particles captured by a well, boundary or zone, or that left the model, are
# not binned: the C++ reference does not count captured particles.
AQUIFER_STATUSES = ("TimeLimitReached", "Stagnated")


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
# 4. Load the mod-PATH3DU reference concentrations
# ──────────────────────────────────────────────────────────────────────

def load_reference_concentrations(path, n_cells):
    """Load the reference concentrations from meuk_reference_concentrations.csv.

    The file lists the cells with any concentration; lines starting with '#'
    describe how it was made.

    Returns
    -------
    ref : dict[str, np.ndarray]
        Simulation name -> concentration per cell, shape (n_cells,), in GSF
        cell order (row 0 = bottom).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Download it from {REFERENCE_URL} into this directory.")
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(line for line in f if not line.startswith("#")))
    header, body = rows[0], rows[1:]
    cell = np.array([int(r[header.index("gsf_cell")]) for r in body])
    ref = {}
    for sim in SIMULATIONS:
        k = header.index(sim["ref_column"])
        conc = np.zeros(n_cells, dtype=np.float64)
        conc[cell] = [float(r[k]) for r in body]
        ref[sim["name"]] = conc
    return ref


# ──────────────────────────────────────────────────────────────────────
# 4b. Pore volumes and mass per particle (as in writeUCNs.for)
#
# The C++ reference concentration of a cell is
#   count x mass per particle / pore volume
# with the pore volume taken from the MODFLOW heads (bottom elevation 0).
# ──────────────────────────────────────────────────────────────────────

def read_modflow_heads(path):
    """Read the MODFLOW binary heads file (one layer, one time).

    The file has a 44-byte record header followed by NROWS*NCOLS float32
    values, row 1 (north) first.

    Returns
    -------
    heads : np.ndarray, shape (nrows, ncols)
        Row 0 = top (north), as stored in the file.
    """
    with open(path, "rb") as f:
        f.seek(HEADS_HEADER_BYTES)
        heads = np.fromfile(f, dtype="<f4", count=NROWS * NCOLS)
    if heads.size != NROWS * NCOLS:
        raise ValueError(f"{path}: expected {NROWS * NCOLS} head values, got {heads.size}")
    return heads.reshape(NROWS, NCOLS).astype(np.float64)


def pore_volume_and_mass_per_particle(heads):
    """Compute the cell pore volumes and the mass carried by one particle.

    pore volume = (head - 0) x cell area x porosity
    mass per particle = mean over the source block of (pore volume x INIT_CONC),
                        divided by (REF_REPEATS x PARTICLES_PER_CELL)

    Parameters
    ----------
    heads : np.ndarray, shape (nrows, ncols)
        Heads as stored in the file, row 0 = top (north).

    Returns
    -------
    pore_volume : np.ndarray, shape (n_cells,)
        Pore volume per cell in GSF cell order (row 0 = bottom).
    mass_per_particle : float
        Mass of one particle for a run of REF_REPEATS repeats.
    """
    volume = heads * CELLSIZE * CELLSIZE * POROSITY
    source_mass = (volume[SOURCE_ROWS, SOURCE_COLS] * INIT_CONC).mean()
    mass_per_particle = source_mass / (REF_REPEATS * PARTICLES_PER_CELL)
    # Same row reversal as for the ASC heads and the reference shapefile.
    return np.flipud(volume).flatten(), mass_per_particle


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
    """Bin the endpoints of particles still in the aquifer into a per-cell count array.

    Uses the cell_id from the last trajectory record (the endpoint)
    and maps it to a grid cell via the pre-built cell→(row,col) table.
    Only particles whose final status is in AQUIFER_STATUSES are binned;
    captured particles and particles that left the model are excluded.

    Parameters
    ----------
    results : list of TrajectoryResult
    cell_row, cell_col : arrays from build_cell_to_rc
    n_cells : total number of cells

    Returns
    -------
    counts : np.ndarray, shape (n_cells,)
        Count of endpoints per cell.
    excluded : dict[str, int]
        Number of particles not binned, per final status.  Particles in the
        aquifer without a valid endpoint cell are listed as "NoValidCell".
    """
    counts = np.zeros(n_cells, dtype=np.float64)
    excluded = {}
    for r in results:
        if r.final_status not in AQUIFER_STATUSES:
            excluded[r.final_status] = excluded.get(r.final_status, 0) + 1
            continue
        records = r.to_records()
        cid = records[-1]["cell_id"] if records else -1
        if 0 <= cid < n_cells:
            counts[cid] += 1.0
        else:
            excluded["NoValidCell"] = excluded.get("NoValidCell", 0) + 1
    return counts, excluded


def counts_to_concentration(counts, pore_volume, mass_per_particle):
    """Convert endpoint counts to concentrations, as writeUCNs.for does.

    The counts are scaled from N_REPEATS to REF_REPEATS repeats first.
    concentration = count x mass per particle / pore volume
    """
    scale = REF_REPEATS / N_REPEATS
    return counts * scale * mass_per_particle / pore_volume


# ──────────────────────────────────────────────────────────────────────
# 7. Validation metrics
# ──────────────────────────────────────────────────────────────────────

def compute_metrics(rust_conc, ref_conc, pore_volume):
    """Compute comparison metrics between two concentration arrays.

    Both arrays are concentrations per cell in the same (GSF) cell order;
    pore_volume is the pore volume per cell in that order.

    Returns
    -------
    dict with keys:
        pearson_r       – Pearson correlation coefficient of the concentrations
        nrmse           – Normalized RMSE of the concentrations (relative to reference range)
        mass_error_pct  – Error in the mass in the aquifer, (Rust - C++) / C++, as a percentage
        rust_mass       – Mass in the aquifer (Rust): sum of concentration x pore volume
        ref_mass        – Mass in the aquifer (reference): sum of concentration x pore volume
    """
    metrics = {}

    ref_mass = (ref_conc * pore_volume).sum()
    rust_mass = (rust_conc * pore_volume).sum()
    metrics["ref_mass"] = ref_mass
    metrics["rust_mass"] = rust_mass

    if ref_mass > 0:
        metrics["mass_error_pct"] = 100.0 * (rust_mass - ref_mass) / ref_mass
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
    out_path = os.path.join(out_dir, "meuk_validation_workflow_head_plot.png")
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

    # ── 3b. Read MODFLOW heads (pore volumes, mass per particle) ──────
    print("Reading MODFLOW heads (pore volumes)...")
    modflow_heads = read_modflow_heads(HEADS_FILE)
    pore_volume, mass_per_particle = pore_volume_and_mass_per_particle(modflow_heads)
    print(f"  Heads range: [{modflow_heads.min():.4f}, {modflow_heads.max():.4f}]  "
          f"Mass per particle ({REF_REPEATS} repeats): {mass_per_particle:.2f}")

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

    # ── 9. Reference concentrations ──────────────────────────────────
    ref_by_sim = load_reference_concentrations(REFERENCE_CSV, n_cells)
    ref_total = REF_REPEATS * len(base_particles)   # particles per end time in the reference

    # ── 10. Run simulations ───────────────────────────────────────────
    # Each base particle is replicated N_REPEATS times with unique IDs.
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

    all_metrics = {}           # (setup, sim_name) -> metrics
    all_results = {}           # (setup, sim_name) -> list[TrajectoryResult]
    all_trajectories = {}      # sim_name -> list of [(x,y),...], first repeat, first set-up

    for setup_name in SETUP_NAMES:
        setup = SETUPS[setup_name]
        for sim in SIMULATIONS:
            sim_name = sim["name"]
            end_time = sim["end_time"]
            print(f"\n{'='*60}")
            print(f"Set-up {setup_name}: {setup['label']}")
            print(f"Simulation: {sim_name}  (t_end = {end_time} d, repeats = {N_REPEATS})")
            print(f"{'='*60}")

            config_dict = {
                "velocity_method": "Waterloo",
                "solver": setup["solver"],
                "adaptive": {
                    "tolerance": ADAPTIVE_TOL,
                    "safety": 0.9,
                    "alpha": 0.2,
                    "min_scale": 0.2,
                    "max_scale": 5.0,
                    "max_rejects": 10,
                    "min_dt": 1e-10,
                    "euler_dt": 1e-10,
                },
                "dispersion": {
                    "method": "Gsde",
                    "alpha_l": DISP_LONGITUDINAL,
                    "alpha_th": DISP_TRANSVERSE_H,
                    "alpha_tv": 0.0,  # must be 0 for an SSP&A field (two-dimensional)
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
                "max_dt": setup["max_dt"],
                "direction": 1.0,
            }
            config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))
            print(f"  Total particles: {total_particles} "
                  f"({len(base_particles)} base × {N_REPEATS} repeats)")

            t0 = time.perf_counter()
            results = mp3du.run_simulation(config, field, particles, parallel=True)
            dt_sim = time.perf_counter() - t0
            print(f"  Simulation complete: {len(results)} trajectories  ({dt_sim:.1f} s)")
            all_results[(setup_name, sim_name)] = results

            # Particle paths of the first repeat, first set-up (head-contour plot)
            if setup_name == SETUP_NAMES[0]:
                all_trajectories[sim_name] = [
                    [(rec["x"], rec["y"]) for rec in r.to_records()]
                    for r in results[:len(base_particles)] if len(r) > 0
                ]

            # Bin the endpoints of particles still in the aquifer and convert
            # the counts to concentrations
            rust_counts, excluded = bin_endpoints(results, cell_row, cell_col, n_cells)
            print(f"  Particles binned (still in the aquifer): "
                  f"{int(rust_counts.sum())} of {total_particles}")
            for status, count in sorted(excluded.items()):
                print(f"    excluded, {status}: {count}")
            rust_conc = counts_to_concentration(rust_counts, pore_volume, mass_per_particle)

            metrics = compute_metrics(rust_conc, ref_by_sim[sim_name], pore_volume)
            metrics["rust_fraction"] = rust_counts.sum() / total_particles
            metrics["ref_fraction"] = metrics["ref_mass"] / (mass_per_particle * ref_total)
            all_metrics[(setup_name, sim_name)] = metrics

            print(f"\n  Validation metrics vs mod-PATH3DU (concentrations):")
            print(f"    Fraction in aquifer:      {metrics['rust_fraction']:.4f}  "
                  f"(mod-PATH3DU {metrics['ref_fraction']:.4f})")
            print(f"    Pearson r:                {metrics['pearson_r']:.4f}")
            print(f"    Norm. RMSE:               {metrics['nrmse']:.4f}")
            print(f"    Mass in aquifer error:    {metrics['mass_error_pct']:+.2f}%  "
                  f"((Rust - C++) / C++)")

    # ── 10b. Summary ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"VALIDATION SUMMARY  (GSDE, {N_REPEATS} repeats; reference: mod-PATH3DU, "
          f"{REF_REPEATS} repeats)")
    print(f"{'='*60}")
    for setup_name in SETUP_NAMES:
        print(f"Set-up {setup_name}: {SETUPS[setup_name]['label']}")
        for sim in SIMULATIONS:
            m = all_metrics[(setup_name, sim["name"])]
            print(f"  {sim['name']}:  in aquifer {m['rust_fraction']:.4f} "
                  f"(mod-PATH3DU {m['ref_fraction']:.4f})  r={m['pearson_r']:.4f}  "
                  f"nRMSE={m['nrmse']:.4f}  mass_err={m['mass_error_pct']:+.2f}%")

    # ── 11. Head-contour + particle-path overlay plot (first set-up) ─────────────────
    _save_head_plot(heads_2d, base_particles, drifts, all_trajectories, SIMULATIONS, MODEL_WS)

    # ── 12. Optional: reference comparison plots ─────────────────────
    try:
        import matplotlib.pyplot as plt

        extent = [XLLCORNER, XLLCORNER + NCOLS * CELLSIZE,
                  YLLCORNER, YLLCORNER + NROWS * CELLSIZE]
        for (setup_name, sim_name), metrics in all_metrics.items():
            ref_grid = ref_by_sim[sim_name].reshape(NROWS, NCOLS)
            rust_counts, _excluded = bin_endpoints(all_results[(setup_name, sim_name)],
                                                   cell_row, cell_col, n_cells)
            rust_grid = counts_to_concentration(rust_counts, pore_volume,
                                                mass_per_particle).reshape(NROWS, NCOLS)

            fig, axes = plt.subplots(1, 3, figsize=(18, 5))
            vmax = max(ref_grid.max(), rust_grid.max(), 1.0)
            axes[0].imshow(ref_grid, origin="lower", extent=extent, vmin=0, vmax=vmax, cmap="hot_r")
            axes[0].set_title("mod-PATH3DU 2.1.9 (reference)")
            axes[1].imshow(rust_grid, origin="lower", extent=extent, vmin=0, vmax=vmax, cmap="hot_r")
            axes[1].set_title(f"MP3DU-RS, {setup_name} (×{N_REPEATS})")
            diff = rust_grid - ref_grid
            dmax = max(abs(diff.min()), abs(diff.max()), 1.0)
            im = axes[2].imshow(diff, origin="lower", extent=extent, vmin=-dmax, vmax=dmax, cmap="RdBu_r")
            axes[2].set_title("Difference (MP3DU-RS − mod-PATH3DU)")
            fig.colorbar(im, ax=axes[2], shrink=0.8)
            for ax in axes:
                ax.set_xlabel("X (m)")
                ax.set_ylabel("Y (m)")
            fig.suptitle(f"Example 5a — {sim_name}, {setup_name}  (r={metrics['pearson_r']:.3f})")
            fig.tight_layout()
            plot_path = os.path.join(MODEL_WS, f"validation_{setup_name}_{sim_name}.png")
            fig.savefig(plot_path, dpi=150)
            plt.close(fig)
            print(f"  Plot saved: {plot_path}")

    except ImportError:
        print("  matplotlib not available — skipping plots")

    print("\nDone.")


if __name__ == "__main__":
    main()
