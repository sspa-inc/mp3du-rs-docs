# Quickstart

Run your first particle tracking simulation in Python.

## Overview

This guide walks through a minimal simulation:

1. Prepare grid geometry and cell data as NumPy arrays
2. Build a grid and hydrate cell properties and flows
3. Fit the Waterloo velocity field
4. Configure simulation parameters
5. Run the simulation and inspect results

!!! tip "Using AI agents?"
    See [AI Agent Prompts](../guides/agent-prompts.md) for copy-paste prompts
    that prime an agent on the `mp3du` docs, inspect a MODFLOW model folder,
    generate starter code, and review or debug the result without drifting back
    to legacy MODPATH assumptions.

## Complete Example

```python
import json
import numpy as np
import mp3du

# ------------------------------------------------------------------
# 1. Grid: 10 x 10 square cells of 10 m (replace with your model's grid)
# ------------------------------------------------------------------
# vertices:  for each cell, its (x, y) corners, listed CLOCKWISE
# centers:   for each cell, (x, y, z) of its centre
# neighbors: for each face of each cell, the neighbouring cell (-1 = none)
nx, ny, d = 10, 10, 10.0
n_cells = nx * ny
vertices, centers, neighbors = [], [], []
for i in range(n_cells):
    col, row = i % nx, i // nx
    x0, y0 = col * d, row * d
    # clockwise, so the faces are: left, top, right, bottom
    vertices.append([(x0, y0), (x0, y0 + d), (x0 + d, y0 + d), (x0 + d, y0)])  # (1)!
    centers.append((x0 + d / 2, y0 + d / 2, 50.0))
    neighbors.append([
        i - 1 if col > 0 else -1,
        i + nx if row < ny - 1 else -1,
        i + 1 if col < nx - 1 else -1,
        i - nx if row > 0 else -1,
    ])

grid = mp3du.build_grid(vertices, centers)
print(f"Grid loaded: {grid.n_cells()} cells")

# ------------------------------------------------------------------
# 2. Hydrate cell properties
# ------------------------------------------------------------------
cell_props = mp3du.hydrate_cell_properties(
    top=np.full(n_cells, 100.0),          # cell top elevations
    bot=np.full(n_cells, 0.0),            # cell bottom elevations
    porosity=np.full(n_cells, 0.30),      # effective porosity
    retardation=np.full(n_cells, 1.0),    # retardation factor
    hhk=np.full(n_cells, 1e-4),           # horizontal hydraulic conductivity
    vhk=np.full(n_cells, 1e-5),           # vertical hydraulic conductivity
    disp_long=np.full(n_cells, 10.0),     # longitudinal dispersivity
    disp_trans_h=np.full(n_cells, 1.0),   # horizontal transverse dispersivity
    disp_trans_v=np.full(n_cells, 0.1),   # vertical transverse dispersivity
)

# ------------------------------------------------------------------
# 3. Hydrate cell flows: uniform flow in +x (replace with your model's flows)
# ------------------------------------------------------------------
# A Darcy flux of 0.1 m/d through a saturated thickness of 95 m carries
# 0.1 * 95 * 10 = 95 m3/d across every vertical face, from left to right.
q_face = 0.1 * 95.0 * d
face_offset = np.arange(0, 4 * n_cells + 1, 4, dtype=np.uint64)  # (2)!
face_neighbor = np.array([m for nbrs in neighbors for m in nbrs], dtype=np.int64)
# positive = INTO the cell: in through the left face, out through the right face
face_flow = np.where(face_neighbor < 0, 0.0,
                     np.tile([q_face, 0.0, -q_face, 0.0], n_cells))
# The left and right columns exchange that flow with a boundary condition
# (for example constant head), passed as q_other (raw MODFLOW sign: + = into the cell)
col = np.arange(n_cells) % nx
q_other = np.where(col == 0, q_face, 0.0) + np.where(col == nx - 1, -q_face, 0.0)

cell_flows = mp3du.hydrate_cell_flows(
    head=np.full(n_cells, 95.0),
    water_table=np.full(n_cells, 95.0),  # placeholder only; real models must derive this from layer type
    q_top=np.zeros(n_cells),
    q_bot=np.zeros(n_cells),
    q_vert=np.zeros(n_cells),             # one layer, no recharge: no vertical flow
    q_well=np.zeros(n_cells),             # raw MODFLOW sign (negative = extraction)
    q_other=q_other,
    q_storage=np.zeros(n_cells),          # steady state
    has_well=np.zeros(n_cells, dtype=np.bool_),
    face_offset=face_offset,
    face_flow=face_flow,                   # mp3du convention: positive = into cell
                                               # (for USG/MF6: pass raw FLOWJA directly;
                                               #  for MF2005: negate assembled per-face values)
    face_neighbor=face_neighbor,
)

# ------------------------------------------------------------------
# 4. Hydrate Waterloo velocity inputs and fit the field
# ------------------------------------------------------------------
# Face end points: each face runs from one vertex to the next
v = np.array(vertices)                     # shape (n_cells, 4, 2)
v_next = np.roll(v, -1, axis=1)
face_vx1, face_vy1 = v[..., 0].ravel(), v[..., 1].ravel()
face_vx2, face_vy2 = v_next[..., 0].ravel(), v_next[..., 1].ravel()
face_length = np.hypot(face_vx2 - face_vx1, face_vy2 - face_vy1)
centers_xy = np.array([[c[0], c[1]] for c in centers])
# radius: 1.1 x the distance from the centre to the farthest vertex
radii = 1.1 * np.hypot(v[..., 0] - centers_xy[:, :1], v[..., 1] - centers_xy[:, 1:]).max(axis=1)

waterloo_inputs = mp3du.hydrate_waterloo_inputs(
    centers_xy=centers_xy,
    radii=radii,
    perimeters=np.full(n_cells, 4 * d),
    areas=np.full(n_cells, d * d),
    q_vert=np.zeros(n_cells),
    q_well=np.zeros(n_cells),              # raw MODFLOW sign — do NOT negate
    q_other=q_other,
    face_offset=face_offset,
    face_vx1=face_vx1,
    face_vy1=face_vy1,
    face_vx2=face_vx2,
    face_vy2=face_vy2,
    face_length=face_length,
    face_flow=face_flow,                   # same array — positive = INTO cell
    noflow_mask=face_neighbor < 0,
)

waterloo_cfg = mp3du.WaterlooConfig(order_of_approx=35, n_control_points=122)
field = mp3du.fit_waterloo(waterloo_cfg, grid, waterloo_inputs, cell_props, cell_flows)
print(f"Field fitted: {field.method_name()}, {field.n_cells()} cells")

# ------------------------------------------------------------------
# 5. Build a simulation configuration from JSON
# ------------------------------------------------------------------
config_dict = {
    "velocity_method": "Waterloo",
    "solver": "DormandPrince",
    "direction": 1.0,
    "initial_dt": 1.0,
    "max_dt": 100.0,
    "retardation_enabled": False,
    "adaptive": {
        "tolerance": 1e-6,
        "safety": 0.9,
        "alpha": 0.2,
        "min_scale": 0.2,
        "max_scale": 5.0,
        "max_rejects": 10,
        "min_dt": 1e-10,
        "euler_dt": 1e-10,
    },
    "dispersion": {"method": "None"},
    "capture": {
        "max_time": 150.0,
        "max_steps": 1000000,
        "stagnation_velocity": 1e-12,
        "stagnation_limit": 100,
        # Optional: capture_radius for weak-sink well behaviour.
        # Omit for strong-sink (capture on cell entry).
        # "capture_radius": 0.5,
    },
}
config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))
config.validate()

# ------------------------------------------------------------------
# 6. Define starting positions and run
# ------------------------------------------------------------------
# z is the LOCAL height in the cell: 0 = bottom, 1 = top (not an elevation).
# cell_id is the cell that contains (x, y): col + nx * row.
particles = [
    mp3du.ParticleStart(id=0, x=15.0, y=25.0, z=0.5, cell_id=21, initial_dt=1.0),
    mp3du.ParticleStart(id=1, x=45.0, y=55.0, z=0.5, cell_id=54, initial_dt=1.0),
]

results = mp3du.run_simulation(config, field, particles, parallel=True)

# ------------------------------------------------------------------
# 7. Inspect results
# ------------------------------------------------------------------
for result in results:
    records = result.to_records()
    print(
        f"Particle {result.particle_id}: "
        f"status={result.final_status}, "
        f"steps={len(result)}"
    )
    if records:
        last = records[-1]
        print(f"  Final position: ({last['x']:.2f}, {last['y']:.2f}, {last['z']:.2f})")
# The seepage velocity is 0.1 / 0.30 = 0.333 m/d, so after 150 days each
# particle should be 50 m further in +x: at x = 65 and x = 95.
```

!!! warning "Do not copy the placeholder `water_table` blindly"
    In a real MODFLOW model, `water_table` is layer-type dependent. Use
    `top` for confined layers, `head` for unconfined layers, and `min(head,
    top)` for convertible layers. See
    [Units & Conventions](../reference/units-and-conventions.md#elevations-and-saturated-thickness)
    before adapting this example to production data.

1. Replace this grid with your model's cell polygons. Vertices must be listed **clockwise**; see [Units & Conventions](../reference/units-and-conventions.md#cell-vertex-winding-order-cw-required).
2. The `face_offset` array uses CSR (Compressed Sparse Row) format: the faces of cell `i` are entries `face_offset[i]` to `face_offset[i+1] - 1` of the face arrays. Here every cell has 4 faces. Every cell needs at least 3 faces. See [Units & Conventions](../reference/units-and-conventions.md#array-ordering) for details.

!!! info "Boundary Conditions"
    For models with boundary conditions (CHD, WEL, RCH, etc.), pass IFACE-based
    boundary data to `hydrate_cell_flows()` to enable face-based particle capture.
    See [IFACE & Boundary Capture](../concepts/iface-boundary-capture.md) and
    [Running Simulations](../guides/running-simulations.md#hydrating-boundary-conditions).

## What's Next?

- [Building Configs](../guides/building-configs.md) — Detailed configuration reference
- [Running Simulations](../guides/running-simulations.md) — Advanced workflows and parallel execution
- [Geometry](../concepts/geometry.md) — How the Waterloo velocity method works
- [Examples](../examples/index.md) — More validated examples
