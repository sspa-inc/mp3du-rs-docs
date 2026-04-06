#!/usr/bin/env python3
"""
Single-Cell Diagnostic — visual sanity check for mp3du particle tracking.
==========================================================================

PURPOSE
-------
Creates one 10×10 rectangular cell with a known, balanced face-flow budget,
fits a Waterloo velocity field, tracks a single particle, and plots
everything together so you can confirm that:

  1. Face-flow signs and directions are physically consistent.
  2. The interpolated velocity field matches the prescribed flow budget.
  3. The particle trajectory follows the expected streamline.

CONVENTIONS DEMONSTRATED (see Units & Conventions reference)
-------------------------------------------------------------
  • Vertices wound clockwise (CW) — required by the Waterloo method.
    (If your data uses CCW winding, negate all face_flow values.)
  • Face index i corresponds to the edge from vertex[i] → vertex[(i+1) % n].
  • z in ParticleStart is LOCAL [0, 1] (0 = cell bottom, 1 = cell top),
    NOT a physical elevation.
  • face_flow sign convention: positive = INTO the cell.
    The same array is passed to both hydrate_cell_flows() and
    hydrate_waterloo_inputs().
  • q_well is passed in raw MODFLOW sign to BOTH functions — never negate it.

FLOW BUDGET
-----------
  Left face  : 1.0 m³/d IN     (the only inflow)
  Right face : 0.5 m³/d OUT
  Top face   : 0.5 m³/d OUT
  Bottom face: 0.0 (no-flow)
  ΣQ_in = 1.0,  ΣQ_out = 0.5 + 0.5 = 1.0  ✓ balanced
  In positive=INTO convention: inflow is +, outflow is −.

EXPECTED RESULT
---------------
  Particle starts near the left face, tracks right and upward (following the
  50/50 split), and exits the domain near the top-right corner.
  Final status: ExitedDomain.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import mp3du

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Configuration — edit these to explore different scenarios          ║
# ╚══════════════════════════════════════════════════════════════════════╝

CELL_SIZE = 10.0          # m — square cell side length
TOP, BOT = 10.0, 0.0      # m — cell top / bottom elevation
POROSITY = 0.25            # dimensionless
HHK = 1e-2                 # m/d — horizontal hydraulic conductivity
VHK = 1e-3                 # m/d — vertical hydraulic conductivity
CENTER_HEAD = 9.0          # m — hydraulic head at cell centre

# Physical flow budget  (positive = INTO the cell)
#   Faces are ordered by CW vertex index: Left(0), Top(1), Right(2), Bottom(3)
Q_LEFT = 1.0               # m³/d — 1.0 IN  (positive = into cell)
Q_TOP = -0.5              # m³/d — 0.5 OUT (negative = out of cell)
Q_RIGHT = -0.5             # m³/d — 0.5 OUT (negative = out of cell)
Q_BOTTOM = 0.0             # m³/d — no flow through bottom face

# Particle start (x, y are physical coordinates; z is LOCAL [0, 1])
PX, PY, PZ = 0.1, 5.0, 0.5

# Waterloo fitting parameters (low order is fine for a simple rectangle)
ORDER_OF_APPROX = 3
N_CONTROL_POINTS = 16

# Output path — SVG is vector, scales perfectly in docs
OUTPUT_PATH = Path(__file__).parent.parent / "assets" / "images" / "single_cell_diagnostic.svg"


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 1 — Build the grid                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝
# Vertices MUST be clockwise (CW) when viewed from above.  For a square:
#   v0=(0,0) → v1=(0,L) → v2=(L,L) → v3=(L,0)
# This gives faces: 0=left, 1=top, 2=right, 3=bottom.
# (If your source data uses CCW winding, reverse the vertex list and
#  negate all face_flow values.)

print(f"mp3du {mp3du.version()}")

L = CELL_SIZE
vertices = [[(0.0, 0.0), (0.0, L), (L, L), (L, 0.0)]]
centers = [(L / 2, L / 2, (TOP + BOT) / 2)]
grid = mp3du.build_grid(vertices, centers)

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 2 — Cell properties                                         ║
# ╚══════════════════════════════════════════════════════════════════════╝

cell_props = mp3du.hydrate_cell_properties(
    top=np.array([TOP]),
    bot=np.array([BOT]),
    porosity=np.array([POROSITY]),
    retardation=np.array([1.0]),
    hhk=np.array([HHK]),
    vhk=np.array([VHK]),
    disp_long=np.array([0.0]),
    disp_trans_h=np.array([0.0]),
    disp_trans_v=np.array([0.0]),
)

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 3 — Face flows                                              ║
# ╚══════════════════════════════════════════════════════════════════════╝
# Convention: positive = INTO cell, negative = OUT of cell.
#
# The SAME face_flow array is passed to both hydrate_cell_flows() and
# hydrate_waterloo_inputs().
#
# For real MODFLOW data, the sign you start with depends on the version:
#   MODFLOW-USG / MF6 FLOW-JA-FACE  → raw positive = INTO  → pass directly
#   MODFLOW-2005 (after directional→per-face assembly) → positive = OUT → negate first
#
# See: https://sspa-inc.github.io/mp3du-rs-docs/reference/units-and-conventions/

# Face order follows CW vertex order: Left(0), Top(1), Right(2), Bottom(3)
face_flow = np.array([Q_LEFT, Q_TOP, Q_RIGHT, Q_BOTTOM], dtype=np.float64)

# Sanity: net flow must balance (mass conservation).
net = face_flow.sum()
assert abs(net) < 1e-12, f"Flow budget not balanced: ΣQ = {net}"

# CSR offset / neighbour arrays for a single cell with 4 faces.
face_offset = np.array([0, 4], dtype=np.uint64)
face_neighbor = np.array([-1, -1, -1, -1], dtype=np.int64)  # all boundary

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 4 — Hydrate cell flows                                      ║
# ╚══════════════════════════════════════════════════════════════════════╝
# water_table rule (from Units & Conventions):
#   confined (laytyp 0)    → top
#   unconfined (laytyp 1)  → head
#   convertible (laytyp>0) → min(head, top)
# Here we treat the cell as unconfined: water_table = top.

cell_flows = mp3du.hydrate_cell_flows(
    head=np.array([CENTER_HEAD]),
    water_table=np.array([TOP]),       # unconfined: use top elevation
    q_top=np.zeros(1),
    q_bot=np.zeros(1),
    q_vert=np.zeros(1),
    q_well=np.zeros(1),               # no wells — raw MODFLOW sign, never negate
    q_other=np.zeros(1),
    q_storage=np.zeros(1),
    has_well=np.zeros(1, dtype=bool),
    face_offset=face_offset,
    face_flow=face_flow,               # ← positive = INTO
    face_neighbor=face_neighbor,
)

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 5 — Hydrate Waterloo velocity-field inputs                   ║
# ╚══════════════════════════════════════════════════════════════════════╝
# face_v{x,y}{1,2} give the (x,y) coordinates of each face's start and
# end vertex — same order as the vertex list.

waterloo_inputs = mp3du.hydrate_waterloo_inputs(
    centers_xy=np.array([[L / 2, L / 2]]),
    radii=np.array([L / 2]),
    perimeters=np.array([4 * L]),
    areas=np.array([L * L]),
    q_vert=np.zeros(1),
    q_well=np.zeros(1),               # raw MODFLOW sign — never negate
    q_other=np.zeros(1),
    face_offset=face_offset,
    face_vx1=np.array([0.0, 0.0, L, L]),       # start-vertex x: left, top, right, bottom
    face_vy1=np.array([0.0, L,   L, 0.0]),      # start-vertex y
    face_vx2=np.array([0.0, L,   L, 0.0]),      # end-vertex x
    face_vy2=np.array([L,   L,   0.0, 0.0]),    # end-vertex y
    face_length=np.array([L, L, L, L]),
    face_flow=face_flow,               # ← same array, positive = INTO
    noflow_mask=np.zeros(4, dtype=bool),
)

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 6 — Fit the Waterloo velocity field                         ║
# ╚══════════════════════════════════════════════════════════════════════╝

waterloo_cfg = mp3du.WaterlooConfig(
    order_of_approx=ORDER_OF_APPROX,
    n_control_points=N_CONTROL_POINTS,
)
field = mp3du.fit_waterloo(waterloo_cfg, grid, waterloo_inputs, cell_props, cell_flows)

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 7 — Simulation configuration                                ║
# ╚══════════════════════════════════════════════════════════════════════╝
# Build via SimulationConfig.from_json() — the canonical pattern.
# direction: 1.0 = forward, -1.0 = backward (only valid values).

config = mp3du.SimulationConfig.from_json(json.dumps({
    "velocity_method": "Waterloo",
    "solver": "DormandPrince",
    "direction": 1.0,
    "initial_dt": 0.5,
    "max_dt": 2.0,
    "retardation_enabled": False,
    "adaptive": {
        "tolerance": 1e-6,
        "safety": 0.9,
        "alpha": 0.2,
        "min_scale": 0.2,
        "max_scale": 5.0,
        "max_rejects": 10,
        "min_dt": 1e-10,
        "euler_dt": 0.1,
    },
    "dispersion": {"method": "None"},
    "capture": {
        "max_time": 500.0,
        "max_steps": 1000,
        "stagnation_velocity": 1e-12,
        "stagnation_limit": 10,
    },
}))

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 8 — Track one particle                                      ║
# ╚══════════════════════════════════════════════════════════════════════╝
# z is LOCAL [0, 1]:  0.5 = mid-layer.  NOT a physical elevation!

particles = [
    mp3du.ParticleStart(id=0, x=PX, y=PY, z=PZ, cell_id=0, initial_dt=0.5),
]
results = mp3du.run_simulation(config, field, particles, parallel=False)
result = results[0]
records = result.to_records()

print(f"Status : {result.final_status}")
print(f"Steps  : {len(records)}")
if records:
    print(f"Start  : ({records[0]['x']:.4f}, {records[0]['y']:.4f})")
    print(f"End    : ({records[-1]['x']:.4f}, {records[-1]['y']:.4f})")

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 9 — Sample the fitted velocity / head fields for plotting      ║
# ╚══════════════════════════════════════════════════════════════════════╝

N_SAMPLE = 30 # Increased resolution for smoother contours
xs_grid = np.linspace(0.1, L - 0.1, N_SAMPLE)
ys_grid = np.linspace(0.1, L - 0.1, N_SAMPLE)
xx, yy = np.meshgrid(xs_grid, ys_grid)
U = np.zeros_like(xx)
V = np.zeros_like(yy)
H = np.zeros_like(xx)

for i in range(xx.shape[0]):
    for j in range(xx.shape[1]):
        vx, vy, _vz = field.velocity_at(float(xx[i, j]), float(yy[i, j]), 0.5)
        U[i, j], V[i, j] = vx, vy
        # Approximate head from Darcy's law:  h ≈ h₀ − (v·Δr)(n/K)
        H[i, j] = CENTER_HEAD - (
            vx * (xx[i, j] - L / 2) + vy * (yy[i, j] - L / 2)
        ) * (POROSITY / HHK)

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Step 10 — Plot (Modernized Aesthetics)                              ║
# ╚══════════════════════════════════════════════════════════════════════╝

# Modern Color Palette
CLR_INFLOW = "#10ac84"    # Mint green
CLR_OUTFLOW = "#ee5253"   # Soft crimson
CLR_NOFLOW = "#c8d6e5"    # Subtle gray-blue
CLR_PATH = "#ff9f43"      # Bright golden orange
CLR_HEAD = "#2e86de"      # Strong vivid blue
CLR_VEL = "#8395a7"       # Cool gray for quivers

fig, ax = plt.subplots(figsize=(10, 10), facecolor="#fdfdfd")
ax.set_facecolor("#ffffff")

# ── Head contours ────────────────────────────────────────────────────
# Popping the contours with higher alpha and thicker lines
cs = ax.contour(xx, yy, H, levels=15, colors=CLR_HEAD, alpha=0.6, linewidths=1.2, zorder=1)

# ── Velocity quivers ─────────────────────────────────────────────────
# Slice the grid [::2, ::2] to show fewer arrows so they don't dominate
skip = (slice(None, None, 2), slice(None, None, 2))
speed = np.sqrt(U**2 + V**2)
ax.quiver(
    xx[skip], yy[skip], (U / speed)[skip], (V / speed)[skip],
    color=CLR_VEL, alpha=0.25, scale=22, width=0.003, headwidth=4, zorder=2,
)

# ── Cell boundary ────────────────────────────────────────────────────
ax.plot([0, L, L, 0, 0], [0, 0, L, L, 0], color="#222f3e", linewidth=2.5, zorder=5)

# ── Face labels + flow arrows ────────────────────────────────────────
face_names = ["Left", "Top", "Right", "Bottom"]
# Unit outward-normal directions for each face (left→−x, top→+y, right→+x, bottom→−y)
normals = [(-1, 0), (0, 1), (1, 0), (0, -1)]
arrow_origins = [(0, L / 2), (L / 2, L), (L, L / 2), (L / 2, 0)]

OFFSET_LABEL = 1.6  # Push labels further out to prevent overlap
OFFSET_ARROW = 0.9  # Keep arrows shorter than labels

label_xy = [
    (-OFFSET_LABEL, L / 2), 
    (L / 2, L + OFFSET_LABEL), 
    (L + OFFSET_LABEL, L / 2), 
    (L / 2, -OFFSET_LABEL)
]

for idx in range(4):
    q = face_flow[idx]
    if abs(q) < 1e-15:
        clr, direction_label = CLR_NOFLOW, "No Flow"
    elif q > 0:
        clr, direction_label = CLR_INFLOW, "IN"
    else:
        clr, direction_label = CLR_OUTFLOW, "OUT"

    # Clean, modern floating labels
    lx, ly = label_xy[idx]
    ax.text(
        lx, ly,
        f"{face_names[idx]}\nQ = {abs(q):.1f} {direction_label}",
        ha="center", va="center", fontsize=10, fontweight="bold", color=clr,
        # ec="none" removes the border, keeping a soft white backing to block gridlines
        bbox=dict(boxstyle="round,pad=0.4", fc="#ffffff", ec="none", alpha=0.85),
    )

    # Fixed Arrow Logic (No overlapping)
    if abs(q) > 1e-15:
        ox, oy = arrow_origins[idx]
        nx, ny = normals[idx]
        
        if q > 0: # INFLOW: Starts outside, points to the edge
            start_x, start_y = ox + nx * OFFSET_ARROW, oy + ny * OFFSET_ARROW
            end_x, end_y = ox, oy
        else:     # OUTFLOW: Starts at the edge, points outside
            start_x, start_y = ox, oy
            end_x, end_y = ox + nx * OFFSET_ARROW, oy + ny * OFFSET_ARROW

        ax.annotate(
            "",
            xy=(end_x, end_y),
            xytext=(start_x, start_y),
            arrowprops=dict(arrowstyle="->,head_width=0.4,head_length=0.6", color=clr, lw=3.0),
            zorder=6
        )

# ── Particle trajectory ─────────────────────────────────────────────
if records:
    traj_x = [r["x"] for r in records]
    traj_y = [r["y"] for r in records]
    
    # 1. Glow Effect (thick, transparent line underneath)
    ax.plot(traj_x, traj_y, color=CLR_PATH, linewidth=7, alpha=0.3, solid_capstyle="round", zorder=6)
    # 2. Main Trajectory Line
    ax.plot(traj_x, traj_y, color=CLR_PATH, linewidth=2.5, solid_capstyle="round", zorder=7, label="Trajectory")
    
    # Start / End markers (slightly larger, cleaner borders)
    ax.scatter(traj_x[0], traj_y[0], color=CLR_INFLOW, s=140, zorder=8,
               edgecolors="white", linewidths=2, label="Start")
    ax.scatter(traj_x[-1], traj_y[-1], color=CLR_OUTFLOW, s=140, zorder=8,
               edgecolors="white", linewidths=2, label="End")

# ── Axes & legend ────────────────────────────────────────────────────
ax.set_xlim(-2.5, L + 2.5)
ax.set_ylim(-2.5, L + 2.5)
ax.set_xlabel("X  [m]", fontsize=11, fontweight="medium", color="#333333")
ax.set_ylabel("Y  [m]", fontsize=11, fontweight="medium", color="#333333")
ax.set_title(
    "Single-Cell Diagnostic\n"
    f"Waterloo order={ORDER_OF_APPROX}  |  Status: {result.final_status}  |  {len(records)} steps",
    fontsize=14, fontweight="bold", color="#222f3e", pad=15
)
ax.set_aspect("equal")

# Clean up grid and spines
ax.grid(True, linewidth=0.5, color="#e1e5ea", linestyle="--")
for spine in ax.spines.values():
    spine.set_color("#d1d8e0")
    spine.set_linewidth(1.5)

ax.legend(loc="lower right", fontsize=10, framealpha=1.0, edgecolor="#d1d8e0", borderpad=0.8)

fig.tight_layout()
fig.savefig(OUTPUT_PATH, bbox_inches="tight", dpi=300)
print(f"Saved -> {OUTPUT_PATH}")