# Quickstart

Run your first particle tracking simulation in Python.

## Overview

This guide walks through a minimal simulation:

1. Prepare grid geometry and cell data as NumPy arrays
2. Build a grid and hydrate cell properties and flows
3. Fit the Waterloo velocity field
4. Configure simulation parameters
5. Run the simulation and inspect results

## Complete Example

```python
import json
import numpy as np
import mp3du

# ------------------------------------------------------------------
# 1. Load your grid and cell data (replace with your actual data)
# ------------------------------------------------------------------
# vertices: list of cells, each cell is a list of (x, y) vertex pairs
# centers:  list of (x, y, z) cell centroids
n_cells = 100
vertices = [
    [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    for _ in range(n_cells)
]  # (1)!
centers = [
    (5.0 + 10.0 * (i % 10), 5.0 + 10.0 * (i // 10), 50.0)
    for i in range(n_cells)
]

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
# 3. Hydrate cell flows
# ------------------------------------------------------------------
# Build face connectivity arrays (CSR format)
face_offset = np.zeros(n_cells + 1, dtype=np.uint64)  # (2)!
face_flow = np.array([], dtype=np.float64)
face_neighbor = np.array([], dtype=np.int64)

cell_flows = mp3du.hydrate_cell_flows(
    head=np.full(n_cells, 95.0),
    water_table=np.full(n_cells, 95.0),
    q_top=np.zeros(n_cells),
    q_bot=np.zeros(n_cells),
    q_vert=np.zeros(n_cells),
    q_well=np.zeros(n_cells),             # raw MODFLOW sign (negative = extraction)
    q_other=np.zeros(n_cells),
    q_storage=np.zeros(n_cells),
    has_well=np.zeros(n_cells, dtype=np.bool_),
    face_offset=face_offset,
    face_flow=face_flow,                   # raw MODFLOW sign (positive = out of cell)
    face_neighbor=face_neighbor,
)

# ------------------------------------------------------------------
# 4. Hydrate Waterloo velocity inputs and fit the field
# ------------------------------------------------------------------
waterloo_inputs = mp3du.hydrate_waterloo_inputs(
    centers_xy=np.array([[c[0], c[1]] for c in centers]),
    radii=np.full(n_cells, 5.0),
    perimeters=np.full(n_cells, 40.0),
    areas=np.full(n_cells, 100.0),
    q_vert=np.zeros(n_cells),
    q_well=np.zeros(n_cells),              # raw MODFLOW sign — do NOT negate
    q_other=np.zeros(n_cells),
    face_offset=face_offset,
    face_vx1=np.array([], dtype=np.float64),
    face_vy1=np.array([], dtype=np.float64),
    face_vx2=np.array([], dtype=np.float64),
    face_vy2=np.array([], dtype=np.float64),
    face_length=np.array([], dtype=np.float64),
    face_flow=-face_flow,                  # NEGATE: Waterloo convention = positive INTO cell
    noflow_mask=np.zeros(0, dtype=np.bool_),
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
        "euler_dt": 0.1,
    },
    "dispersion": {"method": "None"},
    "capture": {
        "max_time": 365000.0,
        "max_steps": 1000000,
        "stagnation_velocity": 1e-12,
        "stagnation_limit": 100,
        # Optional: capture_radius for weak-sink well behaviour.
        # Omit for strong-sink (capture on cell entry).
        # "capture_radius": 0.5,
    },
}
config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))

# ------------------------------------------------------------------
# 6. Define starting positions and run
# ------------------------------------------------------------------
particles = [
    mp3du.ParticleStart(id=0, x=15.0, y=25.0, z=50.0, cell_id=12, initial_dt=1.0),
    mp3du.ParticleStart(id=1, x=45.0, y=55.0, z=50.0, cell_id=54, initial_dt=1.0),
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
```

1. Replace these placeholder vertices with your actual cell vertex coordinates from the MODFLOW-USG grid.
2. The `face_offset` array uses CSR (Compressed Sparse Row) format. See [Units & Conventions](../reference/units-and-conventions.md#array-ordering) for details.

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
