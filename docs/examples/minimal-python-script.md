# Minimal Python Simulation Script

The smallest complete Python script that runs a particle tracking simulation with mod-PATH3DU.

## Script

```python
import json
import numpy as np
import mp3du

# --- 1. Build the grid from vertex and center data ---
# vertices: list of polygons, each polygon is a list of (x, y) tuples
# centers: list of (x, y, z) tuples for cell centroids
vertices = [
    [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)],
]
centers = [(50.0, 50.0, 25.0)]

grid = mp3du.build_grid(vertices, centers)

# --- 2. Hydrate cell properties (one cell) ---
cell_properties = mp3du.hydrate_cell_properties(
    top=np.array([50.0]),
    bot=np.array([0.0]),
    porosity=np.array([0.3]),
    retardation=np.array([1.0]),
    hhk=np.array([1e-4]),
    vhk=np.array([1e-5]),
    disp_long=np.array([0.0]),
    disp_trans_h=np.array([0.0]),
    disp_trans_v=np.array([0.0]),
)

# --- 3. Hydrate cell flows ---
cell_flows = mp3du.hydrate_cell_flows(
    head=np.array([45.0]),
    water_table=np.array([45.0]),
    q_top=np.array([0.0]),
    q_bot=np.array([0.0]),
    q_vert=np.array([0.0]),
    q_well=np.array([0.0]),
    q_other=np.array([0.0]),
    q_storage=np.array([0.0]),
    has_well=np.array([False]),
    face_offset=np.array([0], dtype=np.uint64),
    face_flow=np.array([], dtype=np.float64),
    face_neighbor=np.array([], dtype=np.int64),
)

# --- 4. Hydrate Waterloo velocity inputs ---
fit_inputs = mp3du.hydrate_waterloo_inputs(
    centers_xy=np.array([[50.0, 50.0]]),
    radii=np.array([56.42]),
    perimeters=np.array([400.0]),
    areas=np.array([10000.0]),
    q_vert=np.array([0.0]),
    q_well=np.array([0.0]),
    q_other=np.array([0.0]),
    face_offset=np.array([0], dtype=np.uint64),
    face_vx1=np.array([], dtype=np.float64),
    face_vy1=np.array([], dtype=np.float64),
    face_vx2=np.array([], dtype=np.float64),
    face_vy2=np.array([], dtype=np.float64),
    face_length=np.array([], dtype=np.float64),
    face_flow=np.array([], dtype=np.float64),
    noflow_mask=np.array([], dtype=np.bool_),
)

# --- 5. Fit the Waterloo velocity field ---
waterloo_config = mp3du.WaterlooConfig(order_of_approx=35, n_control_points=122)
field = mp3du.fit_waterloo(waterloo_config, grid, fit_inputs, cell_properties, cell_flows)

# --- 6. Load simulation configuration ---
config = mp3du.SimulationConfig.from_json(json.dumps({
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
        "euler_dt": 1.0
    },
    "dispersion": {"method": "None"},
    "retardation_enabled": False,
    "capture": {
        "max_time": 365250.0,
        "max_steps": 1000000,
        "stagnation_velocity": 1e-12,
        "stagnation_limit": 100
    },
    "initial_dt": 1.0,
    "max_dt": 100.0,
    "direction": 1.0
}))

# --- 7. Define particle starting positions ---
particles = [
    mp3du.ParticleStart(id=0, x=50.0, y=50.0, z=25.0, cell_id=0, initial_dt=1.0),
]

# --- 8. Run the simulation ---
results = mp3du.run_simulation(config, field, particles)

# --- 9. Print results ---
for r in results:
    print(f"Particle {r.particle_id}: status={r.final_status}, steps={len(r)}")
```

## What This Script Does

1. **Builds a grid** from vertex polygons and cell centroids.
2. **Hydrates cell properties** — top/bottom elevations, porosity, hydraulic conductivity.
3. **Hydrates cell flows** — heads, water table, face flows and budgets.
4. **Hydrates Waterloo inputs** — geometric data for the Waterloo velocity interpolation.
5. **Fits the velocity field** using the Waterloo method.
6. **Creates a simulation config** from JSON (DormandPrince solver, forward tracking, no dispersion).
7. **Defines one particle** starting position.
8. **Runs the simulation** and prints the result status.

## Prerequisites

- mod-PATH3DU installed ([Installation Guide](../getting-started/install.md))
- NumPy available (`pip install numpy`)
- Grid geometry and MODFLOW-USG output data available

## See Also

- [Quickstart](../getting-started/quickstart.md) — More detailed tutorial
- [Batch Simulation](batch-simulation.md) — Multiple particles
- [Running Simulations](../guides/running-simulations.md) — Full workflow guide
