# Running Simulations

Python workflow for particle tracking simulations with mod-PATH3DU.

## Workflow Overview

A complete simulation follows these steps:

1. Build the grid from vertex and centroid data
2. Hydrate cell properties (porosity, conductivity, dispersivity, etc.)
3. Hydrate cell flows (heads, face flows, well rates, etc.)
4. Hydrate Waterloo-specific inputs (geometry and face velocities)
5. Fit the Waterloo velocity field
6. Create a `SimulationConfig` from JSON
7. Define particle starting positions
8. Run the simulation
9. Process the results

## Loading Data

### Building the Grid

The grid is constructed from cell vertices and centroids:

```python
import mp3du

# vertices: list of cells, each cell is a list of (x, y) tuples
# centers: list of (x, y, z) tuples — one per cell
grid = mp3du.build_grid(vertices, centers)
print(f"Grid loaded: {grid.n_cells()} cells")
```

- `vertices` — each cell's polygon boundary as ordered $(x, y)$ coordinate pairs
- `centers` — the $(x, y, z)$ centroid of each cell

Both lists must have the same length (one entry per cell).

### Hydrating Cell Properties

Cell properties provide the physical parameters for each cell:

```python
import numpy as np

cell_props = mp3du.hydrate_cell_properties(
    top=top_array,             # cell top elevations (n_cells,)
    bot=bot_array,             # cell bottom elevations (n_cells,)
    porosity=porosity_array,   # effective porosity (n_cells,)
    retardation=retard_array,  # retardation factor (n_cells,)
    hhk=hhk_array,             # horizontal hydraulic conductivity (n_cells,)
    vhk=vhk_array,            # vertical hydraulic conductivity (n_cells,)
    disp_long=dl_array,        # longitudinal dispersivity (n_cells,)
    disp_trans_h=dth_array,    # horizontal transverse dispersivity (n_cells,)
    disp_trans_v=dtv_array,    # vertical transverse dispersivity (n_cells,)
)
```

All arrays must be 1D `numpy.ndarray[float64]` with length equal to `grid.n_cells()`.

### Hydrating Cell Flows

Cell flows provide the hydraulic state and inter-cell fluxes:

```python
cell_flows = mp3du.hydrate_cell_flows(
    head=head_array,               # hydraulic head (n_cells,)
    water_table=wt_array,          # water table elevation (n_cells,)
    q_top=q_top_array,             # top-face recharge flux (n_cells,)
    q_bot=q_bot_array,             # bottom-face flux (n_cells,)
    q_vert=q_vert_array,           # vertical flux (n_cells,)
    q_well=q_well_array,           # well pumping rate (n_cells,)
    q_other=q_other_array,         # other source/sink (n_cells,)
    q_storage=q_storage_array,     # storage flux (n_cells,)
    has_well=has_well_array,       # boolean well presence (n_cells,) bool
    face_offset=face_offset,       # CSR row pointers (n_cells + 1,) uint64
    face_flow=face_flow_array,     # face flow rates (n_faces,) float64
    face_neighbor=face_nbr_array,  # face neighbor cell IDs (n_faces,) int64
)
```

!!! info "CSR face arrays"
    The `face_offset`, `face_flow`, and `face_neighbor` arrays use Compressed Sparse Row format. For cell $i$, its face connections span indices `face_offset[i]` to `face_offset[i+1]`. See [Units & Conventions](../reference/units-and-conventions.md#array-ordering) for details.

### Hydrating Boundary Conditions

For models with IFACE-assigned boundary conditions (CHD, WEL, RCH, etc.),
pass boundary metadata to enable face-based particle capture:

```python
import numpy as np

# Assemble parallel boundary condition arrays from MODFLOW CBC output.
# Each entry represents one BC record: (cell_index, iface, flow, type_index).
bc_cell_ids = []
bc_iface_arr = []
bc_flow_arr = []
bc_type_id_arr = []
bc_type_names = ["CONSTANT HEAD", "WELLS", "RECHARGE"]

# Example: CHD cells with IFACE = 2 (side face)
for node, flow in chd_flows.items():
    bc_cell_ids.append(node - 1)     # 0-based
    bc_iface_arr.append(2)
    bc_flow_arr.append(flow)          # raw MODFLOW sign
    bc_type_id_arr.append(0)          # index into bc_type_names

cell_flows = mp3du.hydrate_cell_flows(
    head=head_array,
    water_table=wt_array,
    q_top=q_top_array,
    q_bot=q_bot_array,
    q_vert=q_vert_array,
    q_well=q_well_array,
    q_other=q_other_array,
    q_storage=q_storage_array,
    has_well=has_well_array,
    face_offset=face_offset,
    face_flow=face_flow_array,
    face_neighbor=face_nbr_array,
    # Boundary condition metadata (optional — omit for legacy behaviour)
    bc_cell_ids=np.array(bc_cell_ids, dtype=np.int64),
    bc_iface=np.array(bc_iface_arr, dtype=np.int32),
    bc_flow=np.array(bc_flow_arr, dtype=np.float64),
    bc_type_id=np.array(bc_type_id_arr, dtype=np.int32),
    bc_type_names=bc_type_names,
    is_domain_boundary=domain_bdy_arr,        # bool (n_cells,)
    has_water_table=water_table_flags,         # bool (n_cells,)
)
```

!!! tip "IFACE flow routing helper"
    The `scripts/mp3du_iface_routing.py` module provides `route_iface_bc_flows()`,
    a vectorized helper that routes IFACE-tagged BC flows to the correct
    `q_well` / `q_other` / `q_top` / `q_bot` arrays. See
    [IFACE Flow Routing](../reference/iface-flow-routing.md) for details.

!!! info "All `bc_*` arrays are optional"
    If you omit all boundary arrays, `hydrate_cell_flows()` behaves exactly
    as before — capture is controlled by `has_well` alone.
    See [IFACE & Boundary Capture](../concepts/iface-boundary-capture.md)
    for the full conceptual guide.

### Hydrating Waterloo Inputs

The Waterloo method requires additional geometric and velocity data per cell:

```python
waterloo_inputs = mp3du.hydrate_waterloo_inputs(
    centers_xy=centers_xy,     # cell centroids (n_cells, 2) float64
    radii=radii,               # effective cell radii (n_cells,) float64
    perimeters=perimeters,     # cell perimeters (n_cells,) float64
    areas=areas,               # cell plan-view areas (n_cells,) float64
    q_vert=q_vert,             # vertical flux (n_cells,) float64
    q_well=q_well,             # well flux (n_cells,) float64
    q_other=q_other,           # other flux (n_cells,) float64
    face_offset=face_offset,   # CSR row pointers (n_cells + 1,) uint64
    face_vx1=face_vx1,         # face velocity x-component, node 1 (n_faces,) float64
    face_vy1=face_vy1,         # face velocity y-component, node 1 (n_faces,) float64
    face_vx2=face_vx2,         # face velocity x-component, node 2 (n_faces,) float64
    face_vy2=face_vy2,         # face velocity y-component, node 2 (n_faces,) float64
    face_length=face_length,   # face lengths (n_faces,) float64
    face_flow=face_flow,       # face flow rates (n_faces,) float64
    noflow_mask=noflow_mask,   # no-flow face flags (n_faces,) bool
)
```

## Fitting the Velocity Field

Once all input data is hydrated, fit the Waterloo velocity field:

```python
waterloo_cfg = mp3du.WaterlooConfig(order_of_approx=35, n_control_points=122)

field = mp3du.fit_waterloo(
    waterloo_cfg, grid, waterloo_inputs, cell_props, cell_flows
)
print(f"Field: {field.method_name()}, {field.n_cells()} cells")
```

The fitting step computes polynomial velocity coefficients for every cell. This is the most computationally expensive setup step — it only needs to be done once per flow field configuration.

## Creating the Configuration

Build the configuration as a Python dictionary and convert to `SimulationConfig`:

```python
import json

config_dict = {
    "velocity_method": "Waterloo",
    "solver": "DormandPrince",
    "direction": 1.0,
    "initial_dt": 1.0,
    "max_dt": 1000.0,
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
    },
}

config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))
config.validate()
```

See [Building Configs](building-configs.md) for detailed field-by-field guidance.

## Defining Particle Starting Positions

Each particle needs an ID, starting coordinates, containing cell, and initial time step:

```python
particles = [
    mp3du.ParticleStart(
        id=0,
        x=150.0,
        y=250.0,
        z=50.0,
        cell_id=42,
        initial_dt=1.0,
    ),
    mp3du.ParticleStart(
        id=1,
        x=300.0,
        y=400.0,
        z=45.0,
        cell_id=87,
        initial_dt=1.0,
    ),
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique particle identifier |
| `x`, `y`, `z` | float | Starting coordinates (must be inside the specified cell) |
| `cell_id` | int | 0-based index of the cell containing the start point |
| `initial_dt` | float | Initial time step for this particle |

!!! warning "Coordinates must be inside the specified cell"
    If the starting position is outside `cell_id`, the solver may produce incorrect results or raise an error. Verify your starting coordinates against the grid geometry.

## Running the Simulation

### Serial Execution

```python
results = mp3du.run_simulation(config, field, particles, parallel=False)
```

### Parallel Execution

By default, particles are tracked in parallel using all available CPU cores (via Rayon):

```python
results = mp3du.run_simulation(config, field, particles, parallel=True)
```

Parallel execution provides near-linear speedup for large particle sets. The velocity field is shared read-only across threads.

!!! tip
    Use `parallel=True` (the default) for production runs with many particles. Use `parallel=False` for debugging, where deterministic single-threaded execution simplifies diagnosis.

## Interpreting Results

### TrajectoryResult

Each particle produces a `TrajectoryResult`:

```python
for result in results:
    print(f"Particle {result.particle_id}")
    print(f"  Status: {result.final_status}")
    print(f"  Reason: {result.termination_reason}")
    print(f"  Steps:  {len(result)}")

    # Get trajectory as a list of record dicts
    records = result.to_records()
    if records:
        first = records[0]
        last = records[-1]
        print(f"  Start:  ({first['x']:.2f}, {first['y']:.2f}, {first['z']:.2f}) t={first['time']:.2f}")
        print(f"  End:    ({last['x']:.2f}, {last['y']:.2f}, {last['z']:.2f}) t={last['time']:.2f}")
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `particle_id` | int | The particle's ID (matches `ParticleStart.id`) |
| `final_status` | str | Termination reason (see below) |
| `termination_reason` | str | Detailed capture description (e.g., `"Internal sink/source: CONSTANT HEAD"`) |
| `to_records()` | list[dict] | Trajectory as a list of record dictionaries |
| `len(result)` | int | Number of trajectory points |

### Trajectory Records

Each record dictionary from `to_records()` contains:

| Key | Type | Description |
|-----|------|-------------|
| `step` | int | Integration step number |
| `time` | float | Simulation time |
| `x`, `y`, `z` | float | Particle position |
| `vx`, `vy`, `vz` | float | Velocity components at position |
| `cell_id` | int | Cell containing the particle |
| `dt` | float | Time step used |

### Final Status Values

| Status | Meaning |
|--------|---------|
| `CapturedByWell` | Particle reached a well (IFACE 0) within capture radius |
| `CapturedByBoundary` | Particle terminated by an IFACE 2/5/6/7 boundary condition |
| `CapturedAtModelEdge` | Particle reached a domain-edge cell (`is_domain_boundary = True`) |
| `Exited` | Particle left the grid domain |
| `MaxTime` | `capture.max_time` was reached |
| `MaxSteps` | `capture.max_steps` was reached |
| `Stagnated` | Velocity below `stagnation_velocity` for `stagnation_limit` consecutive steps |
| `Error` | A solver error occurred (check error diagnostics) |

!!! info "termination_reason"
    For `CapturedByWell` and `CapturedByBoundary`, `termination_reason`
    includes the BC type name from `bc_type_names`, e.g.,
    `"Internal sink/source: CONSTANT HEAD"`. For other statuses it mirrors
    `final_status`.

## Error Handling

Simulation errors are reported via the `final_status` field or raised as Python exceptions during setup. Common errors:

- **Invalid configuration** — raised by `SimulationConfig.from_json()` or `validate()`
- **Array shape mismatch** — raised by `hydrate_*` functions when array lengths don't match
- **Solver failure** — reported as `final_status = "Error"` in the trajectory result

See [Error Diagnostics](../reference/error-diagnostics.md) for the full error catalog and [Troubleshooting](troubleshooting.md) for common problems and solutions.
