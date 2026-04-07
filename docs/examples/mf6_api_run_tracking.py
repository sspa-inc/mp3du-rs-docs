"""
Run MODFLOW 6 API + mp3du-rs particle tracking for Example 1b.

This script demonstrates the modern, all-API workflow for coupled groundwater
flow and particle tracking—no binary file I/O required.

Key Concepts:
-------------
1. **FLOW-JA-FACE Sign Convention**: MODFLOW 6 `FLOWJA` uses positive = INTO cell.
   The mp3du-rs API also uses positive = INTO cell. Pass `FLOWJA` directly without
   any negation.

2. **Extracting Boundary Flows via API**: Use `SIMVALS` (computed flow rates),
   NOT `RHS` (matrix right-hand side) when reading CHD flows.

3. **IFACE-Based Capture**: CHD cells use IFACE=2 for lateral boundary capture.
   This allows particles to exist within CHD cells and only captures them when
   they exit through the appropriate face.

Workflow:
1. Load the DISV geometry written by create_model.py
2. Initialize MODFLOW 6 through the shared-library API
3. Read heads, FLOW-JA-FACE, and package rates directly from MF6 memory
4. Build mp3du flow structures and fit the Waterloo velocity field
5. Track particles with mp3du.run_simulation()
6. Save trajectories.csv, capture_summary.csv, and particle_paths.png
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
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.patches import Patch, Polygon as MplPolygon
from matplotlib.tri import LinearTriInterpolator, Triangulation

SCRIPT_DIR = Path(__file__).resolve().parent
SIM_WS = SCRIPT_DIR / "sim"
META_PATH = SIM_WS / "grid_meta.json"
POLY_PATH = SIM_WS / "cell_polygons.json"
PARTICLE_SHP = SCRIPT_DIR / "PartStart_Intersect.shp"
CPP_PATHLINE_SHP = SCRIPT_DIR / "voronoi_v2_Pathline.shp"


def find_libmf6():
    """Locate the MODFLOW 6 shared library."""
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
        "Cannot find libmf6. Set LIBMF6_PATH or run:\n"
        "  python -m flopy.utils.get_modflow <dir> --repo modflow6"
    )


def load_grid_data():
    """Load grid metadata and cell polygons from JSON files."""
    with META_PATH.open() as f:
        meta = json.load(f)
    with POLY_PATH.open() as f:
        poly_data = json.load(f)
    cell_polygons_2d = [np.array(p, dtype=float) for p in poly_data["polygons"]]
    centers_2d = np.array(poly_data["centers_xy"], dtype=float)
    return meta, poly_data, cell_polygons_2d, centers_2d


def signed_area_xy(poly):
    """Compute signed area of a polygon."""
    area = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    return 0.5 * area


def build_mp3du_grid(meta, cell_polygons_2d, centers_2d):
    """Build mp3du grid structures from MF6 geometry."""
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
    """Build mp3du cell properties array."""
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
    """Precompute geometric quantities for flow extraction."""
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
    """Map MF6 FLOWJA indices to mp3du face indices."""
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
    """Extract flows from MF6 and build mp3du flow structures."""
    n_cells = geo["n_cells"]
    face_flow_into_arr = np.zeros(len(geo["face_neighbor_arr"]), dtype=float)
    interior_mask = flow_map["hface_japos"] >= 0

    # MF6 FLOWJA positive = INTO owning cell. Keep the same positive-into-cell
    # convention for both hydrate calls.
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
    """Load particle starting locations from shapefile."""
    sf = shapefile.Reader(str(PARTICLE_SHP))
    particles = []
    for i, rec in enumerate(sf.iterShapeRecords()):
        attrs = rec.record.as_dict()
        x, y = rec.shape.points[0]
        cell_id = int(attrs["P3D_CellID"]) - 1
        z = float(attrs.get("ZLOC", 0.5) or 0.5)
        particles.append(mp3du.ParticleStart(id=i, x=x, y=y, z=z, cell_id=cell_id, initial_dt=0.1))
    return particles


def save_outputs(results, meta, particles, cell_vertices_list, left_chd_cells, right_chd_cells, well_cells, head_arr):
    """Save trajectory data and create visualization."""
    # Save trajectories
    traj_path = SCRIPT_DIR / "trajectories.csv"
    with traj_path.open("w") as f:
        header_written = False
        for r in results:
            for rec in r.to_records():
                if not header_written:
                    f.write("particle_id," + ",".join(rec.keys()) + "\n")
                    header_written = True
                f.write(",".join([str(r.particle_id)] + [str(v) for v in rec.values()]) + "\n")

    # Save capture summary
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

    # ── Modern, clean visualization ──────────────────────────────────────────
    plt.rcParams.update({
        "font.family": "sans-serif",
        "axes.spines.top": False,
        "axes.spines.right": False,
    })

    # Figure sized for 5:1 domain aspect ratio with breathing room
    fig, ax = plt.subplots(figsize=(13, 4.5))
    fig.patch.set_facecolor("#f8f8f8")
    ax.set_facecolor("#f8f8f8")

    # ── Head contours on a clipped regular grid (no edge artifacts) ──────────
    centers_xy = np.array([[c[0], c[1]] for c in meta["centers_xy"]], dtype=float)
    triang = Triangulation(centers_xy[:, 0], centers_xy[:, 1])
    interp = LinearTriInterpolator(triang, head_arr)

    # Regular grid strictly inside the domain
    xi = np.linspace(0, 500, 400)
    yi = np.linspace(0, 100, 160)
    Xi, Yi = np.meshgrid(xi, yi)
    Zi = interp(Xi, Yi)

    n_levels = 10
    contour_levels = np.linspace(float(np.nanmin(Zi)), float(np.nanmax(Zi)), n_levels + 1)
    tric = ax.contour(
        Xi, Yi, Zi,
        levels=contour_levels,
        colors="#4a6fa5",
        linewidths=0.75,
        alpha=0.7,
        zorder=2,
    )
    # Sparse, non-overlapping contour labels
    ax.clabel(
        tric,
        inline=True,
        fontsize=6.5,
        fmt="%.1f m",
        inline_spacing=4,
        use_clabeltext=True,
    )

    # ── Voronoi grid edges (very subtle) ─────────────────────────────────────
    grid_segments = []
    for verts in cell_vertices_list:
        n = len(verts)
        for j in range(n):
            grid_segments.append([verts[j], verts[(j + 1) % n]])
    grid_lc = LineCollection(
        grid_segments, linewidths=0.15, colors="#cccccc", zorder=1
    )
    ax.add_collection(grid_lc)

    # ── Boundary condition cells ──────────────────────────────────────────────
    legend_handles = []

    # ── Left CHD cells ────────────────────────────────────────────────────────
    left_patches = [MplPolygon(cell_vertices_list[ci], closed=True) for ci in sorted(left_chd_cells)]
    if left_patches:
        pc_left = PatchCollection(
            left_patches, facecolor="#5b9bd5", edgecolor="none", alpha=0.35, zorder=3
        )
        ax.add_collection(pc_left)
        legend_handles.append(Patch(facecolor="#5b9bd5", alpha=0.5, label="Constant Head"))

    # ── Right CHD cells ───────────────────────────────────────────────────────
    right_patches = [MplPolygon(cell_vertices_list[ci], closed=True) for ci in sorted(right_chd_cells)]
    if right_patches:
        pc_right = PatchCollection(
            right_patches, facecolor="#5b9bd5", edgecolor="none", alpha=0.35, zorder=3
        )
        ax.add_collection(pc_right)

    # ── CHD head value annotations ────────────────────────────────────────────
    left_head = float(meta.get("left_chd_head", 50.0))
    right_head = float(meta.get("right_chd_head", 45.0))
    if left_chd_cells:
        verts = np.array(cell_vertices_list[sorted(left_chd_cells)[len(left_chd_cells) // 2]], dtype=float)
        cx, cy = float(np.mean(verts[:, 0])), float(np.mean(verts[:, 1]))
        ax.text(cx + 3, cy - 10, f"Left CHD = {left_head:.1f} m",
                color="navy", fontsize=7.5, fontweight="bold", zorder=7,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7))
    if right_chd_cells:
        verts = np.array(cell_vertices_list[sorted(right_chd_cells)[len(right_chd_cells) // 2]], dtype=float)
        cx, cy = float(np.mean(verts[:, 0])), float(np.mean(verts[:, 1]))
        ax.text(cx - 45, cy - 10, f"Right CHD = {right_head:.1f} m",
                color="navy", fontsize=7.5, fontweight="bold", zorder=7,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7))

    # ── Well cells ────────────────────────────────────────────────────────────
    well_patches = [MplPolygon(cell_vertices_list[ci], closed=True) for ci in sorted(well_cells)]
    if well_patches:
        pc_well = PatchCollection(
            well_patches, facecolor="#e05c5c", edgecolor="none", alpha=0.55, zorder=3
        )
        ax.add_collection(pc_well)
        legend_handles.append(Patch(facecolor="#e05c5c", alpha=0.6, label="Well"))

    # ── Particle start locations ──────────────────────────────────────────────
    start_xs = [p.x for p in particles]
    start_ys = [p.y for p in particles]
    h_start = ax.scatter(
        start_xs, start_ys,
        s=22, facecolors="none", edgecolors="#2ca02c",
        linewidths=1.2, zorder=6, label="Start locations",
    )
    legend_handles.append(h_start)

    # ── mp3du-rs pathlines — per-particle, solid lines ────────────────────────
    colors = plt.cm.tab10.colors
    for i, r in enumerate(results):
        records = r.to_records()
        if not records:
            continue
        xs = [rec["x"] for rec in records]
        ys = [rec["y"] for rec in records]
        h, = ax.plot(
            xs, ys,
            color=colors[i % len(colors)],
            linewidth=1.1, alpha=0.9,
            zorder=5,
            label=f"mp3du-rs P{r.particle_id}",
        )
        legend_handles.append(h)

    # ── C++ legacy pathlines for comparison — per-particle, dashed ───────────
    if CPP_PATHLINE_SHP.exists():
        cpp_sf = shapefile.Reader(str(CPP_PATHLINE_SHP))
        for i, sr in enumerate(cpp_sf.iterShapeRecords()):
            pts = sr.shape.points
            attrs = sr.record.as_dict()
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            h, = ax.plot(
                xs, ys,
                color=colors[i % len(colors)],
                linewidth=1.4, linestyle="--", alpha=0.6,
                zorder=4,
                label=f"C++ P{attrs.get('PID', i)}",
            )
            legend_handles.append(h)

    # ── Axes, labels, legend ──────────────────────────────────────────────────
    ax.set_xlim(0, 500)
    ax.set_ylim(0, 100)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)", fontsize=9, labelpad=4)
    ax.set_ylabel("y (m)", fontsize=9, labelpad=4)
    ax.set_title(
        "Example 1b — MF6 API · mp3du-rs vs C++ Particle Paths (MF6 Head Contours)",
        fontsize=10, fontweight="bold", pad=8,
    )
    ax.tick_params(labelsize=8)

    leg = ax.legend(
        handles=legend_handles,
        loc="upper left",
        fontsize=7,
        ncol=3,
        framealpha=0.88,
        edgecolor="#cccccc",
        borderpad=0.6,
        labelspacing=0.35,
        columnspacing=1.0,
    )
    leg.get_frame().set_linewidth(0.5)

    fig.tight_layout(pad=0.8)
    fig.savefig(SCRIPT_DIR / "particle_paths.svg", bbox_inches="tight")
    print(f"Saved plot to {SCRIPT_DIR / 'particle_paths.svg'}")


def main():
    """Main workflow: MF6 API solve → mp3du tracking."""
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

    print("Initializing MF6 via API...")
    mf6 = ModflowApi(libmf6_path, working_directory=str(SIM_WS))
    mf6.initialize()
    try:
        print("Reading IA/JA connectivity...")
        ia = mf6.get_value("GWF/CON/IA").copy() - 1
        ja = mf6.get_value("GWF/CON/JA").copy() - 1
        flow_map = precompute_flow_mappings(geo, ia, ja)

        print("Solving flow (one time step)...")
        mf6.update()
        
        print("Extracting heads and FLOWJA from memory...")
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

        print("Reading WEL package data from API...")
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

        print("Reading CHD package data from API...")
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
        
        print("Fitting Waterloo velocity field...")
        waterloo_cfg = mp3du.WaterlooConfig(order_of_approx=35, n_control_points=122)
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
        save_outputs(
            results, meta, particles, cell_vertices_list,
            meta["left_chd_cells"],
            meta["right_chd_cells"],
            {meta["well_cell_2d"]},
            head_arr,
        )
        print("Tracking workflow completed successfully.")
    finally:
        print("Finalizing MF6...")
        mf6.finalize()


if __name__ == "__main__":
    main()
