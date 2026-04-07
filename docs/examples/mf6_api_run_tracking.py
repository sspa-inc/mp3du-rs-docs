"""
Run the MODFLOW 6 API + mp3du workflow for the MF6 version of Example 1b.

This script demonstrates how to couple mp3du-rs with a running MODFLOW 6 simulation
using the modflowapi. It extracts geometry, heads, and flows directly from memory
without reading binary output files.

Key Concepts for LLMs and Developers:
-------------------------------------
1. **FLOW-JA-FACE Sign Convention**: MODFLOW 6 `FLOWJA` uses positive = INTO cell.
   The mp3du-rs API also uses positive = INTO cell. Therefore, you pass the `FLOWJA`
   array directly to both `hydrate_cell_flows` and `hydrate_waterloo_inputs` without
   any negation.

2. **Extracting Boundary Flows via API**: When reading boundary condition flows (like CHD)
   via the MF6 API, do NOT use the `RHS` array. The `RHS` array contains the right-hand
   side of the matrix equation, not the actual computed flow rate. Instead, use the
   `SIMVALS` array, which contains the computed flow rates for the boundary condition
   after the time step is solved.

3. **Domain Boundaries vs. IFACE Capture**: Do NOT mark cells as domain boundaries
   (`is_domain_boundary_arr = True`) if particles need to start inside them or pass
   through them. Particles entering a domain boundary cell are immediately terminated
   with `CapturedAtModelEdge`. Instead, rely on IFACE-based capture (e.g., IFACE=2 for
   lateral CHD flow) which allows particles to exist within the cell and only captures
   them when they exit the appropriate face.

Workflow:
1. Load the DISV geometry written by create_model.py.
2. Initialize MODFLOW 6 through the shared-library API.
3. Read heads, FLOW-JA-FACE, and package rates directly from MF6 memory.
4. Build mp3du.hydrate_cell_flows() and mp3du.hydrate_waterloo_inputs().
5. Fit the Waterloo velocity field with mp3du.fit_waterloo().
6. Track particles with mp3du.run_simulation().
7. Save trajectories.csv, capture_summary.csv, and particle_paths.png.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import mp3du
import numpy as np
import shapefile
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch, Polygon as MplPolygon
from matplotlib.collections import PatchCollection

SCRIPT_DIR = Path(__file__).resolve().parent
SIM_WS = SCRIPT_DIR / "sim"
META_PATH = SIM_WS / "grid_meta.json"
POLY_PATH = SIM_WS / "cell_polygons.json"
PARTICLE_SHP = SCRIPT_DIR / "PartStart_Intersect.shp"
CPP_PATHLINE_SHP = SCRIPT_DIR / "voronoi_v2_Pathline.shp"


def find_libmf6():
    env = os.environ.get("LIBMF6_PATH")
    if env and Path(env).exists():
        return str(env)
    candidate = Path(os.environ.get("TEMP", "/tmp")) / "mf6api" / "libmf6.dll"
    if candidate.exists():
        return str(candidate)
    candidate_linux = Path(os.environ.get("TEMP", "/tmp")) / "mf6api" / "libmf6.so"
    if candidate_linux.exists():
        return str(candidate_linux)
    raise FileNotFoundError(
        "Cannot find libmf6. Set LIBMF6_PATH or run `python -m flopy.utils.get_modflow <dir> --repo modflow6`."
    )


def load_grid_data():
    with META_PATH.open() as f:
        meta = json.load(f)
    with POLY_PATH.open() as f:
        poly_data = json.load(f)
    cell_polygons_2d = [np.array(p, dtype=float) for p in poly_data["polygons"]]
    centers_2d = np.array(poly_data["centers_xy"], dtype=float)
    return meta, poly_data, cell_polygons_2d, centers_2d


def signed_area_xy(poly):
    area = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    return 0.5 * area


def build_mp3du_grid(meta, cell_polygons_2d, centers_2d):
    cell_vertices_list = []
    cell_centers_list = []
    top = meta["layer_top"][0]
    bot = meta["layer_bot"][0]
    zmid = 0.5 * (top + bot)
    for ic in range(meta["ncpl"]):
        verts = [(float(v[0]), float(v[1])) for v in cell_polygons_2d[ic]]
        if signed_area_xy(verts) > 0.0:
            verts = list(reversed(verts))
        cell_vertices_list.append(verts)
        cell_centers_list.append((float(centers_2d[ic, 0]), float(centers_2d[ic, 1]), zmid))
    return cell_vertices_list, cell_centers_list


def build_cell_properties(meta):
    n_cells = meta["ncpl"] * meta["nlay"]
    return mp3du.hydrate_cell_properties(
        top=np.full(n_cells, meta["layer_top"][0], dtype=float),
        bot=np.full(n_cells, meta["layer_bot"][0], dtype=float),
        porosity=np.full(n_cells, meta["porosity"][0], dtype=float),
        retardation=np.ones(n_cells, dtype=float),
        hhk=np.full(n_cells, meta["hk"][0], dtype=float),
        vhk=np.full(n_cells, meta["vka"][0], dtype=float),
        disp_long=np.zeros(n_cells, dtype=float),
        disp_trans_h=np.zeros(n_cells, dtype=float),
        disp_trans_v=np.zeros(n_cells, dtype=float),
    )


def precompute_geometry(meta, cell_polygons_2d):
    ncpl = meta["ncpl"]
    nlay = meta["nlay"]
    n_cells = ncpl * nlay

    edge_lookup = {}
    for ic, poly in enumerate(cell_polygons_2d):
        nv = len(poly)
        for j in range(nv):
            p1 = tuple(np.round(poly[j], 10))
            p2 = tuple(np.round(poly[(j + 1) % nv], 10))
            key = tuple(sorted((p1, p2)))
            edge_lookup.setdefault(key, []).append((ic, j))

    neighbor_2d = [[] for _ in range(ncpl)]
    for ic, poly in enumerate(cell_polygons_2d):
        neighbor_2d[ic] = [-1] * len(poly)

    for entries in edge_lookup.values():
        if len(entries) == 2:
            (c0, f0), (c1, f1) = entries
            neighbor_2d[c0][f0] = c1
            neighbor_2d[c1][f1] = c0

    areas_3d = np.zeros(n_cells)
    perimeters_3d = np.zeros(n_cells)
    radii_3d = np.zeros(n_cells)
    centers_xy_3d = np.zeros((n_cells, 2))
    face_offsets = [0]
    face_vx1 = []
    face_vy1 = []
    face_vx2 = []
    face_vy2 = []
    face_length = []
    face_neighbor = []
    noflow_mask = []

    for ic, poly in enumerate(cell_polygons_2d):
        verts = [(float(v[0]), float(v[1])) for v in poly]
        if signed_area_xy(verts) > 0.0:
            verts = list(reversed(verts))
            nbrs = list(reversed(neighbor_2d[ic]))
        else:
            nbrs = list(neighbor_2d[ic])

        area = 0.0
        perimeter = 0.0
        nv = len(verts)
        for j in range(nv):
            x0, y0 = verts[j]
            x1, y1 = verts[(j + 1) % nv]
            area += x0 * y1 - x1 * y0
            fl = math.hypot(x1 - x0, y1 - y0)
            perimeter += fl
            face_vx1.append(x0)
            face_vy1.append(y0)
            face_vx2.append(x1)
            face_vy2.append(y1)
            face_length.append(fl)
            face_neighbor.append(nbrs[j])
            noflow_mask.append(nbrs[j] < 0)
        areas_3d[ic] = abs(area) / 2.0
        perimeters_3d[ic] = perimeter
        radii_3d[ic] = math.sqrt(areas_3d[ic] / math.pi)
        centers_xy_3d[ic] = [float(np.mean(poly[:, 0])), float(np.mean(poly[:, 1]))]
        face_offsets.append(face_offsets[-1] + nv)

    return {
        "ncpl": ncpl,
        "nlay": nlay,
        "n_cells": n_cells,
        "neighbor_2d": neighbor_2d,
        "areas_3d": areas_3d,
        "perimeters_3d": perimeters_3d,
        "radii_3d": radii_3d,
        "centers_xy_3d": centers_xy_3d,
        "face_offsets": face_offsets,
        "face_offset_arr": np.array(face_offsets, dtype=np.uint64),
        "face_vx1": np.array(face_vx1, dtype=float),
        "face_vy1": np.array(face_vy1, dtype=float),
        "face_vx2": np.array(face_vx2, dtype=float),
        "face_vy2": np.array(face_vy2, dtype=float),
        "face_length": np.array(face_length, dtype=float),
        "face_neighbor_arr": np.array(face_neighbor, dtype=np.int64),
        "noflow_mask": np.array(noflow_mask, dtype=np.bool_),
    }


def precompute_flow_mappings(geo, ia, ja):
    n_cells = geo["n_cells"]
    nbr_to_japos = [None] * n_cells
    for ci in range(n_cells):
        lookup = {}
        for pos in range(ia[ci], ia[ci + 1]):
            nbr = ja[pos]
            if nbr != ci:
                lookup[nbr] = pos
        nbr_to_japos[ci] = lookup

    hface_idx = []
    hface_japos = []
    for ci in range(n_cells):
        lookup = nbr_to_japos[ci]
        start = geo["face_offsets"][ci]
        stop = geo["face_offsets"][ci + 1]
        for local_face, nbr in enumerate(geo["face_neighbor_arr"][start:stop]):
            face_idx = start + local_face
            hface_idx.append(face_idx)
            hface_japos.append(lookup.get(int(nbr), -1) if nbr >= 0 else -1)

    return {
        "hface_idx": np.array(hface_idx, dtype=np.intp),
        "hface_japos": np.array(hface_japos, dtype=np.intp),
    }


def extract_steady_flows(
    geo,
    flow_map,
    head_arr,
    flowja,
    q_well_arr,
    has_well_arr,
    q_chd_arr,
    bc_cell_ids_arr,
    bc_iface_arr,
    bc_flow_arr,
    bc_type_id_arr,
    bc_type_names,
    is_domain_boundary_arr,
):
    n_cells = geo["n_cells"]
    face_flow_into_arr = np.zeros(len(geo["face_neighbor_arr"]), dtype=float)
    interior_mask = flow_map["hface_japos"] >= 0

    # MF6 FLOWJA positive = INTO owning cell. Keep the same positive-into-cell
    # convention for both hydrate calls so face arrays stay aligned with the
    # CW mp3du geometry contract.
    face_flow_into_arr[flow_map["hface_idx"][interior_mask]] = flowja[flow_map["hface_japos"][interior_mask]]

    q_top_arr = np.zeros(n_cells, dtype=float)
    q_bot_arr = np.zeros(n_cells, dtype=float)
    q_vert_arr = q_top_arr - q_bot_arr

    cell_flows = mp3du.hydrate_cell_flows(
        head=head_arr,
        water_table=head_arr.copy(),
        q_top=q_top_arr,
        q_bot=q_bot_arr,
        q_vert=q_vert_arr,
        q_well=q_well_arr,
        q_other=q_chd_arr,
        q_storage=np.zeros(n_cells, dtype=float),
        has_well=has_well_arr,
        face_offset=geo["face_offset_arr"],
        face_flow=face_flow_into_arr,
        face_neighbor=geo["face_neighbor_arr"],
        bc_cell_ids=bc_cell_ids_arr,
        bc_iface=bc_iface_arr,
        bc_flow=bc_flow_arr,
        bc_type_id=bc_type_id_arr,
        bc_type_names=bc_type_names,
        is_domain_boundary=is_domain_boundary_arr,
    )

    waterloo_inputs = mp3du.hydrate_waterloo_inputs(
        centers_xy=geo["centers_xy_3d"],
        radii=geo["radii_3d"],
        perimeters=geo["perimeters_3d"],
        areas=geo["areas_3d"],
        q_vert=q_vert_arr,
        q_well=q_well_arr,
        q_other=q_chd_arr,
        face_offset=geo["face_offset_arr"],
        face_vx1=geo["face_vx1"],
        face_vy1=geo["face_vy1"],
        face_vx2=geo["face_vx2"],
        face_vy2=geo["face_vy2"],
        face_length=geo["face_length"],
        face_flow=face_flow_into_arr,
        noflow_mask=geo["noflow_mask"],
    )
    return cell_flows, waterloo_inputs


def load_particles():
    sf = shapefile.Reader(str(PARTICLE_SHP))
    particles = []
    for i, rec in enumerate(sf.iterShapeRecords()):
        attrs = rec.record.as_dict()
        x, y = rec.shape.points[0]
        cell_id = int(attrs["P3D_CellID"]) - 1
        z = float(attrs.get("ZLOC", 0.5) or 0.5)
        particles.append(mp3du.ParticleStart(id=i, x=x, y=y, z=z, cell_id=cell_id, initial_dt=0.1))
    return particles


def read_generated_chd_labels():
    chd_path = SIM_WS / "gwf.chd"
    labels = []
    if not chd_path.exists():
        return labels

    with chd_path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                layer_1based = int(parts[0])
                cell_1based = int(parts[1])
                head = float(parts[2])
                labels.append((layer_1based - 1, cell_1based - 1, head))
    return labels



def save_outputs(results, meta, particles, cell_vertices_list, chd_cells, well_cells, head_arr):
    traj_path = SCRIPT_DIR / "trajectories.csv"
    with traj_path.open("w") as f:
        header_written = False
        for r in results:
            for rec in r.to_records():
                if not header_written:
                    f.write("particle_id," + ",".join(rec.keys()) + "\n")
                    header_written = True
                f.write(",".join([str(r.particle_id)] + [str(v) for v in rec.values()]) + "\n")

    capture_summary = []
    for r in results:
        records = r.to_records()
        last = records[-1] if records else {}
        capture_summary.append(
            {
                "particle_id": r.particle_id,
                "final_status": r.final_status,
                "x": last.get("x"),
                "y": last.get("y"),
                "z": last.get("z"),
                "cell_id": last.get("cell_id"),
                "steps": len(records),
            }
        )
    cap_path = SCRIPT_DIR / "capture_summary.csv"
    with cap_path.open("w") as f:
        cols = list(capture_summary[0].keys())
        f.write(",".join(cols) + "\n")
        for rec in capture_summary:
            f.write(",".join(str(rec[c]) for c in cols) + "\n")

    fig, ax = plt.subplots(figsize=(14, 5))

    centers_xy = np.array([[c[0], c[1]] for c in meta["centers_xy"]], dtype=float)
    contour_levels = np.linspace(float(np.min(head_arr)), float(np.max(head_arr)), 11)
    tric = ax.tricontour(
        centers_xy[:, 0],
        centers_xy[:, 1],
        head_arr,
        levels=contour_levels,
        colors="0.35",
        linewidths=0.8,
        zorder=0,
    )
    ax.clabel(tric, inline=True, fontsize=7, fmt="%.2f")

    grid_segments = []
    for verts in cell_vertices_list:
        for j in range(len(verts)):
            grid_segments.append([verts[j], verts[(j + 1) % len(verts)]])
    grid_lc = LineCollection(grid_segments, linewidths=0.2, colors="0.80", zorder=1)
    ax.add_collection(grid_lc)

    chd_patches = [MplPolygon(cell_vertices_list[ci], closed=True) for ci in sorted(chd_cells)]
    if chd_patches:
        pc_chd = PatchCollection(chd_patches, facecolor="cornflowerblue", edgecolor="none", alpha=0.5, zorder=2)
        ax.add_collection(pc_chd)

    well_patches = [MplPolygon(cell_vertices_list[ci], closed=True) for ci in sorted(well_cells)]
    if well_patches:
        pc_well = PatchCollection(well_patches, facecolor="red", edgecolor="none", alpha=0.5, zorder=2)
        ax.add_collection(pc_well)

    legend_handles = []
    if chd_patches:
        legend_handles.append(Patch(facecolor="cornflowerblue", alpha=0.5, label="Constant Head"))
    if well_patches:
        legend_handles.append(Patch(facecolor="red", alpha=0.5, label="Well"))

    start_xs = [p.x for p in particles]
    start_ys = [p.y for p in particles]
    h_start = ax.scatter(start_xs, start_ys, s=60, facecolors="none", edgecolors="green", linewidths=1.5, zorder=5)
    legend_handles.append(h_start)
    legend_handles[-1].set_label("Start locations")

    colors = plt.cm.tab10.colors
    for i, r in enumerate(results):
        records = r.to_records()
        if not records:
            continue
        xs = [rec["x"] for rec in records]
        ys = [rec["y"] for rec in records]
        h, = ax.plot(xs, ys, color=colors[i % len(colors)], linewidth=1.0, zorder=4, label=f"Rust P{r.particle_id}")
        legend_handles.append(h)

    if CPP_PATHLINE_SHP.exists():
        cpp_sf = shapefile.Reader(str(CPP_PATHLINE_SHP))
        for i, sr in enumerate(cpp_sf.iterShapeRecords()):
            pts = sr.shape.points
            attrs = sr.record.as_dict()
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            h, = ax.plot(xs, ys, color=colors[i % len(colors)], linewidth=1.5, linestyle="--", zorder=3, label=f"C++ P{attrs['PID']}")
            legend_handles.append(h)

    chd_labels = read_generated_chd_labels()
    left_label_done = False
    right_label_done = False
    for _, cell_id, head in chd_labels:
        if cell_id < 0 or cell_id >= len(cell_vertices_list):
            continue
        verts = np.array(cell_vertices_list[cell_id], dtype=float)
        cx = float(np.mean(verts[:, 0]))
        cy = float(np.mean(verts[:, 1]))
        if abs(head - 50.0) < 1.0e-9 and not left_label_done:
            ax.text(cx + 4.0, cy + 2.0, f"Left CHD = {head:.1f} m", color="navy", fontsize=8, weight="bold", zorder=6)
            left_label_done = True
        elif abs(head - 45.0) < 1.0e-9 and not right_label_done:
            ax.text(cx - 42.0, cy + 2.0, f"Right CHD = {head:.1f} m", color="navy", fontsize=8, weight="bold", zorder=6)
            right_label_done = True
        if left_label_done and right_label_done:
            break

    ax.set_xlim(-5, 510)
    ax.set_ylim(-5, 110)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Example 1b MF6 API — Rust vs C++ Particle Paths with Head Diagnostics")
    ax.legend(handles=legend_handles, loc="upper left", fontsize=6, ncol=3, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(SCRIPT_DIR / "particle_paths.png", dpi=200)
    print(f"Saved comparison plot to {SCRIPT_DIR / 'particle_paths.png'}")


def main():
    print(f"Running from {SCRIPT_DIR}")
    if not (SIM_WS / "mfsim.nam").exists():
        print("ERROR: Model not found. Run create_model.py first.")
        sys.exit(1)

    print("Locating libmf6...")
    libmf6_path = find_libmf6()
    print(f"Using libmf6: {libmf6_path}")
    from modflowapi import ModflowApi

    print("Loading grid data...")
    meta, _, cell_polygons_2d, centers_2d = load_grid_data()
    cell_vertices_list, cell_centers_list = build_mp3du_grid(meta, cell_polygons_2d, centers_2d)
    geo = precompute_geometry(meta, cell_polygons_2d)

    print("Constructing ModflowApi...")
    mf6 = ModflowApi(libmf6_path, working_directory=str(SIM_WS))
    print("Initializing MF6...")
    mf6.initialize()
    try:
        print("Reading IA/JA...")
        ia = mf6.get_value("GWF/CON/IA").copy() - 1
        ja = mf6.get_value("GWF/CON/JA").copy() - 1
        flow_map = precompute_flow_mappings(geo, ia, ja)

        print("Advancing MF6 one step...")
        mf6.update()
        print("Reading heads and FLOWJA...")
        head_arr = mf6.get_value("GWF/X").copy().astype(np.float64)
        flowja = mf6.get_value("GWF/FLOWJA").copy().astype(np.float64)

        n_cells = geo["n_cells"]
        q_well_arr = np.zeros(n_cells, dtype=float)
        has_well_arr = np.zeros(n_cells, dtype=np.bool_)
        q_chd_arr = np.zeros(n_cells, dtype=float)
        is_domain_boundary_arr = np.zeros(n_cells, dtype=np.bool_)
        bc_type_names = ["CONSTANT HEAD", "WELLS"]
        bc_cell_ids_list = []
        bc_iface_list = []
        bc_flow_list = []
        bc_type_id_list = []

        print("Reading WEL package data...")
        nbound_wel = int(mf6.get_value("GWF/WEL_0/NBOUND")[0])
        if nbound_wel > 0:
            nodelist = mf6.get_value("GWF/WEL_0/NODELIST").copy()
            q_vals = mf6.get_value("GWF/WEL_0/Q").copy()
            for i in range(nbound_wel):
                node = int(nodelist[i]) - 1
                q = float(q_vals[i])
                q_well_arr[node] += q
                has_well_arr[node] = True
                bc_cell_ids_list.append(node)
                bc_iface_list.append(0)
                bc_flow_list.append(q)
                bc_type_id_list.append(1)

        print("Reading CHD package data...")
        nbound_chd = int(mf6.get_value("GWF/CHD_0/NBOUND")[0])
        if nbound_chd > 0:
            nodelist = mf6.get_value("GWF/CHD_0/NODELIST").copy()
            simvals = mf6.get_value("GWF/CHD_0/SIMVALS").copy()
            for i in range(nbound_chd):
                node = int(nodelist[i]) - 1
                q = float(simvals[i])
                q_chd_arr[node] += q
                bc_cell_ids_list.append(node)
                bc_iface_list.append(2)
                bc_flow_list.append(q)
                bc_type_id_list.append(0)

        # Do not mark CHD cells as domain boundaries, otherwise particles
        # starting in them will be immediately captured.
        # for node in meta.get("chd_cells", []):
        #     if 0 <= int(node) < n_cells and not has_well_arr[int(node)]:
        #         is_domain_boundary_arr[int(node)] = True

        bc_cell_ids_arr = np.array(bc_cell_ids_list, dtype=np.int64)
        bc_iface_arr = np.array(bc_iface_list, dtype=np.int32)
        bc_flow_arr = np.array(bc_flow_list, dtype=np.float64)
        bc_type_id_arr = np.array(bc_type_id_list, dtype=np.int32)

        print("Building mp3du grid and properties...")
        grid = mp3du.build_grid(cell_vertices_list, cell_centers_list)
        cell_props = build_cell_properties(meta)
        cell_flows, waterloo_inputs = extract_steady_flows(
            geo,
            flow_map,
            head_arr,
            flowja,
            q_well_arr,
            has_well_arr,
            q_chd_arr,
            bc_cell_ids_arr,
            bc_iface_arr,
            bc_flow_arr,
            bc_type_id_arr,
            bc_type_names,
            is_domain_boundary_arr,
        )
        waterloo_cfg = mp3du.WaterlooConfig(order_of_approx=35, n_control_points=122)
        print("Fitting Waterloo field...")
        field = mp3du.fit_waterloo(waterloo_cfg, grid, waterloo_inputs, cell_props, cell_flows)

        config_dict = {
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
                "max_time": 365250.0,
                "max_steps": 1000000,
                "stagnation_velocity": 1e-12,
                "stagnation_limit": 100,
                "capture_radius": 0.5,
            },
            "initial_dt": 0.1,
            "max_dt": 100.0,
            "direction": 1.0,
        }
        config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))
        particles = load_particles()
        print(f"Running particle tracking for {len(particles)} particles...")
        results = mp3du.run_simulation(config, field, particles, parallel=True)
        meta["centers_xy"] = centers_2d.tolist()
        save_outputs(results, meta, particles, cell_vertices_list, set(meta["left_chd_cells"] + meta["right_chd_cells"]), {meta["well_cell_2d"]}, head_arr)
        print("Tracking workflow completed.")
    finally:
        print("Finalizing MF6...")
        mf6.finalize()


if __name__ == "__main__":
    main()
