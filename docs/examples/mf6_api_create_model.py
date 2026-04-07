"""
Create a MODFLOW 6 DISV model for Example 1b (MF6 API version).

This script builds the MF6 model from the Voronoi geometry in mp3du.gsf,
replicating the original Example 1b conceptual model:

- Voronoi DISV grid (~400 cells, single layer)
- Domain: 500 m × 100 m × 50 m
- Top = 50 m, bottom = 0 m
- Constant-head boundaries: Left = 50 m, Right = 45 m
- One pumping well: Q = -50 m³/d (cell 361)
- Uniform HK = 10 m/d, VKA = 1 m/d, porosity = 0.30

Outputs written to the local sim/ folder:
- mfsim.nam and MF6 input files
- grid_meta.json (metadata for mp3du)
- cell_polygons.json (cell geometry for mp3du)
"""

from __future__ import annotations

import json
from pathlib import Path

import flopy
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
SIM_WS = SCRIPT_DIR / "sim"
GSF_PATH = SCRIPT_DIR / "mp3du.gsf"

# Model parameters matching original Example 1b
TOP = 50.0
BOT = 0.0
HK = 10.0
VKA = 1.0
POROSITY = 0.30

# Boundary conditions from original Example 1b (Voronoi.CHD / Voronoi.WEL)
LEFT_CHD_HEAD = 50.0
RIGHT_CHD_HEAD = 45.0
WELL_Q = -50.0
WELL_CELL = 360  # 0-based (361 in 1-based)

# Exact CHD cell IDs (0-based) from the original Voronoi.CHD file.
# These must match the GSF cell ordering — do NOT use heuristic selection.
LEFT_CHD_CELLS = [0, 1, 4, 5, 10, 16, 17, 18, 19, 20, 21, 28, 29, 30, 31, 32, 49]
RIGHT_CHD_CELLS = [643, 660, 684, 707, 727, 744, 760, 773, 786, 797, 807, 816, 824, 831, 836, 840, 842]


def signed_area_xy(vertices: list[tuple[float, float]]) -> float:
    """Compute signed area of a polygon (positive = CCW, negative = CW)."""
    area = 0.0
    n = len(vertices)
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    return 0.5 * area


def parse_gsf(path: Path):
    """Parse a GSF (Grid Specification File) to extract vertices and cells."""
    with path.open() as f:
        lines = f.readlines()

    n_verts = int(lines[1].strip())
    vertices_xy: dict[int, tuple[float, float]] = {}
    for i in range(2, 2 + n_verts):
        parts = lines[i].split()
        vid = int(parts[0])
        vertices_xy[vid] = (float(parts[1]), float(parts[2]))

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
        verts = [vertices_xy[vid] for vid in vert_ids]
        # MF6 DISV expects clockwise vertex order in CELL2D.
        if signed_area_xy(verts) > 0.0:
            vert_ids = list(reversed(vert_ids))
            neighbor_ids = list(reversed(neighbor_ids))
            verts = list(reversed(verts))
        cells.append(
            {
                "id": cell_id,
                "cx": cx,
                "cy": cy,
                "vert_ids": vert_ids,
                "neighbor_ids": neighbor_ids,
                "verts": verts,
            }
        )
    return vertices_xy, cells


def build_disv_geometry(vertices_xy, cells):
    """Convert GSF geometry to MF6 DISV format."""
    vertex_ids = sorted(vertices_xy)
    vid_to_zero = {vid: i for i, vid in enumerate(vertex_ids)}
    vertices = [(vid_to_zero[vid], xy[0], xy[1]) for vid, xy in sorted(vertices_xy.items())]

    cell2d = []
    polygons = []
    centers_xy = []
    for icell2d, cell in enumerate(cells):
        iverts = [vid_to_zero[vid] for vid in cell["vert_ids"]]
        cell2d.append((icell2d, cell["cx"], cell["cy"], len(iverts), *iverts))
        polygons.append([[float(x), float(y)] for x, y in cell["verts"]])
        centers_xy.append([float(cell["cx"]), float(cell["cy"])])
    return vertices, cell2d, polygons, centers_xy


def build_model():
    """Build and write the MF6 DISV model."""
    SIM_WS.mkdir(exist_ok=True)

    vertices_xy, cells = parse_gsf(GSF_PATH)
    vertices, cell2d, polygons, centers_xy_list = build_disv_geometry(vertices_xy, cells)
    ncpl = len(cells)

    # Use exact CHD cell IDs from the original Voronoi.CHD file
    left_chd_cells = list(LEFT_CHD_CELLS)
    right_chd_cells = list(RIGHT_CHD_CELLS)

    # Create MF6 simulation
    sim = flopy.mf6.MFSimulation(
        sim_name="example1b_mf6",
        sim_ws=str(SIM_WS),
        exe_name="mf6",
    )
    flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(1.0, 1, 1.0)], time_units="days")
    flopy.mf6.ModflowIms(
        sim,
        complexity="SIMPLE",
        outer_maximum=200,
        inner_maximum=200,
        outer_dvclose=1.0e-8,
        inner_dvclose=1.0e-10,
        linear_acceleration="BICGSTAB",
    )

    gwf = flopy.mf6.ModflowGwf(sim, modelname="gwf", save_flows=True)
    flopy.mf6.ModflowGwfdisv(
        gwf,
        nlay=1,
        ncpl=ncpl,
        nvert=len(vertices),
        top=np.full(ncpl, TOP),
        botm=np.full((1, ncpl), BOT),
        vertices=vertices,
        cell2d=cell2d,
        length_units="meters",
    )
    flopy.mf6.ModflowGwfic(gwf, strt=np.full(ncpl, TOP))
    flopy.mf6.ModflowGwfnpf(
        gwf,
        icelltype=np.zeros((1, ncpl), dtype=int),
        k=np.full((1, ncpl), HK),
        k33=np.full((1, ncpl), VKA),
        save_specific_discharge=True,
    )

    # CHD package - constant head boundaries
    chd_spd = []
    for node0 in left_chd_cells:
        chd_spd.append(((0, node0), LEFT_CHD_HEAD))
    for node0 in right_chd_cells:
        chd_spd.append(((0, node0), RIGHT_CHD_HEAD))
    flopy.mf6.ModflowGwfchd(gwf, stress_period_data={0: chd_spd}, pname="CHD_0")

    # WEL package - pumping well
    wel_spd = [((0, WELL_CELL), WELL_Q)]
    flopy.mf6.ModflowGwfwel(gwf, stress_period_data={0: wel_spd}, pname="WEL_0")

    flopy.mf6.ModflowGwfoc(gwf)
    sim.write_simulation()

    # Write metadata for mp3du
    well_xy = [float(cells[WELL_CELL]["cx"]), float(cells[WELL_CELL]["cy"])]
    meta = {
        "grid_type": "DISV",
        "nlay": 1,
        "ncpl": ncpl,
        "layer_top": [TOP],
        "layer_bot": [BOT],
        "hk": [HK],
        "vka": [VKA],
        "porosity": [POROSITY],
        "well_q": WELL_Q,
        "well_cell_2d": WELL_CELL,
        "well_xy": well_xy,
        "left_chd_cells": left_chd_cells,
        "right_chd_cells": right_chd_cells,
        "chd_cells": left_chd_cells + right_chd_cells,
        "left_chd_head": LEFT_CHD_HEAD,
        "right_chd_head": RIGHT_CHD_HEAD,
    }
    with (SIM_WS / "grid_meta.json").open("w") as f:
        json.dump(meta, f, indent=2)

    poly_data = {
        "ncpl": ncpl,
        "centers_xy": centers_xy_list,
        "polygons": polygons,
    }
    with (SIM_WS / "cell_polygons.json").open("w") as f:
        json.dump(poly_data, f)

    print(f"Created MF6 DISV model with {ncpl} cells")
    print(f"  Left CHD cells:  {len(left_chd_cells)} (head = {LEFT_CHD_HEAD} m)")
    print(f"  Right CHD cells: {len(right_chd_cells)} (head = {RIGHT_CHD_HEAD} m)")
    print(f"  Well cell:       {WELL_CELL} at ({well_xy[0]:.2f}, {well_xy[1]:.2f}), Q = {WELL_Q} m³/d")
    print(f"  Simulation dir:  {SIM_WS}")


if __name__ == "__main__":
    build_model()
