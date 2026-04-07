"""
Create a MODFLOW 6 DISV version of Example 1b inside [Examples/Example1b/mf6_api](Examples/Example1b/mf6_api).

This script reuses the original Voronoi geometry from [Examples/Example1b/mp3du.gsf](Examples/Example1b/mp3du.gsf)
and rebuilds the MF6 model from the original Example 1b boundary-condition files:

- [Examples/Example1b/Voronoi.CHD](../Voronoi.CHD)
- [Examples/Example1b/Voronoi.WEL](../Voronoi.WEL)

The goal is to preserve the original conceptual model exactly:
- Voronoi DISV grid from the original GSF geometry
- Top = 50 m, bottom = 0 m
- Constant-head boundaries from the original CHD package
- One pumping well from the original WEL package (node 361, Q = -50)
- Uniform HK = 10 m/d, VKA = 1 m/d, porosity = 0.30

Outputs written to the local [sim](Examples/Example1b/mf6_api/sim) folder:
- [mfsim.nam](Examples/Example1b/mf6_api/sim/mfsim.nam) and MF6 input files
- [grid_meta.json](Examples/Example1b/mf6_api/sim/grid_meta.json)
- [cell_polygons.json](Examples/Example1b/mf6_api/sim/cell_polygons.json)
"""

from __future__ import annotations

import json
from pathlib import Path

import flopy
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
SIM_WS = SCRIPT_DIR / "sim"
GSF_PATH = SCRIPT_DIR / "mp3du.gsf"
CHD_PATH = SCRIPT_DIR.parent / "Voronoi.CHD"
WEL_PATH = SCRIPT_DIR.parent / "Voronoi.WEL"

TOP = 50.0
BOT = 0.0
HK = 10.0
VKA = 1.0
POROSITY = 0.30


def signed_area_xy(vertices: list[tuple[float, float]]) -> float:
    area = 0.0
    n = len(vertices)
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    return 0.5 * area


def parse_gsf(path: Path):
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
        centers_xy.append([float(cell["cx"]), float(cell["cy"])] )
    return vertices, cell2d, polygons, centers_xy


def parse_chd(path: Path):
    with path.open() as f:
        lines = [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]

    maxbound, _ = map(int, lines[0].split()[:2])
    _ = lines[1]  # stress-period header
    records = []
    for line in lines[2:2 + maxbound]:
        node, shead, ehead = line.split()[:3]
        records.append((int(node) - 1, float(shead), float(ehead)))
    return records


def parse_wel(path: Path):
    with path.open() as f:
        lines = [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]

    mxactw, _ = map(int, lines[0].split()[:2])
    _ = lines[1]  # stress-period header
    records = []
    for line in lines[2:2 + mxactw]:
        node, q = line.split()[:2]
        records.append((int(node) - 1, float(q)))
    return records


def build_model():
    SIM_WS.mkdir(exist_ok=True)

    vertices_xy, cells = parse_gsf(GSF_PATH)
    vertices, cell2d, polygons, centers_xy_list = build_disv_geometry(vertices_xy, cells)
    ncpl = len(cells)

    chd_records = parse_chd(CHD_PATH)
    wel_records = parse_wel(WEL_PATH)

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

    chd_spd = [((0, node0), shead) for node0, shead, _ in chd_records]
    flopy.mf6.ModflowGwfchd(gwf, stress_period_data={0: chd_spd}, pname="CHD_0")

    wel_spd = [((0, node0), q) for node0, q in wel_records]
    flopy.mf6.ModflowGwfwel(gwf, stress_period_data={0: wel_spd}, pname="WEL_0")

    flopy.mf6.ModflowGwfoc(gwf)
    sim.write_simulation()

    left_chd_cells = [node0 for node0, shead, _ in chd_records if abs(shead - 50.0) < 1.0e-9]
    right_chd_cells = [node0 for node0, shead, _ in chd_records if abs(shead - 45.0) < 1.0e-9]
    well_cell = wel_records[0][0]
    well_xy = [float(cells[well_cell]["cx"]), float(cells[well_cell]["cy"])]

    meta = {
        "grid_type": "DISV",
        "nlay": 1,
        "ncpl": ncpl,
        "layer_top": [TOP],
        "layer_bot": [BOT],
        "hk": [HK],
        "vka": [VKA],
        "porosity": [POROSITY],
        "well_q": wel_records[0][1],
        "well_cell_2d": well_cell,
        "well_xy": well_xy,
        "left_chd_cells": left_chd_cells,
        "right_chd_cells": right_chd_cells,
        "chd_cells": [node0 for node0, _, _ in chd_records],
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
    print(f"  CHD cells:       {len(chd_records)}")
    print(f"  Well cell:       {well_cell} at ({well_xy[0]:.2f}, {well_xy[1]:.2f})")
    print(f"  Simulation dir:  {SIM_WS}")


if __name__ == "__main__":
    build_model()
