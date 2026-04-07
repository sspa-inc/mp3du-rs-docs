# SSP&A: Particle Tracking from Water Level Maps

## Minimal SSP&A Example

This minimal example demonstrates the core SSP&A (S.S. Papadopulos & Associates) workflow using hardcoded data.

```python
import json
import numpy as np
import mp3du

# 1. Build a simple 2x2 grid
vertices = [
    [(0,0), (10,0), (10,10), (0,10)],
    [(10,0), (20,0), (20,10), (10,10)],
    [(0,10), (10,10), (10,20), (0,20)],
    [(10,10), (20,10), (20,20), (10,20)],
]
centers = [(5.0, 5.0, 5.0), (15.0, 5.0, 5.0), (5.0, 15.0, 5.0), (15.0, 15.0, 5.0)]
grid = mp3du.build_grid(vertices, centers)

# 2. Prepare inputs (4 cells)
heads = np.array([10.0, 9.0, 10.0, 9.0])
porosity = np.array([0.2, 0.2, 0.2, 0.2])
well_mask = np.array([False, False, False, True])  # Well in cell 3

# 3. Hydrate inputs
inputs = mp3du.hydrate_sspa_inputs(
    heads=heads,
    porosity=porosity,
    well_mask=well_mask,
    hhk=np.array([1.0, 1.0, 1.0, 1.0]),  # OR hydraulic_conductivity=
)

# 4. Define drifts
drifts = [{"type": "well", "event": "SS", "term": 1, "name": "W1",
           "value": -50.0, "x": 15.0, "y": 15.0}]

# 5. Fit velocity field (consumes grid!)
cfg = mp3du.SspaConfig(search_radius=50.0, krig_offset=0.1)
field = mp3du.fit_sspa(cfg, grid, inputs, drifts)
# grid is now invalid — do not reuse

# 6. Run simulation
sim_cfg = mp3du.SimulationConfig.from_json(json.dumps({
    "velocity_method": "Waterloo",
    "solver": "DormandPrince",
    "adaptive": {"tolerance": 1e-6},
    "capture": {"max_time": 3650.0, "max_steps": 100000},
    "initial_dt": 0.1,
    "direction": 1.0,
}))
particles = [mp3du.ParticleStart(id=0, x=5.0, y=5.0, z=0.5, cell_id=0, initial_dt=0.1)]
results = mp3du.run_simulation(sim_cfg, field, particles)
for r in results:
    print(r.final_status, len(r.to_records()), "steps")
```

## Full MEUK Walkthrough

### Overview
This walkthrough demonstrates a complete workflow for tracking particles from a regional water level map, similar to the MEUK (Modèle d'Écoulement des eaux souterraines de l'Université de Kinshasa) equivalent model in `Examples/Example5a/02-MEUK_Equivalent/`.

### 1. Parse the Grid (GSF)
First, we load the model geometry from a GSF file.
```python
# (Assume parse_gsf is a helper function that reads the GSF file)
vertices, centers = parse_gsf("model.gsf")
grid = mp3du.build_grid(vertices, centers)
```

### 2. Load Heads from ASC Raster
Next, we load the interpolated hydraulic heads from an ASC raster file.
```python
# (Assume load_asc is a helper function)
heads = load_asc("heads.asc")
```

### 3. Load Well Drifts from CSV
We load the pumping well definitions from a CSV file and format them as a list of dictionaries.
```python
import csv
drifts = []
with open("wells.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        drifts.append({
            "type": "well",
            "event": "SS",
            "term": 1,
            "name": row["Name"],
            "value": float(row["Value"]),
            "x": float(row["X"]),
            "y": float(row["Y"]),
        })
```

### 4. Build the Well Mask
We create a boolean array over cells (a 1D array covering all cells) indicating which cells contain wells. This tells the kriging algorithm to ignore the local gradients in these cells, as they are dominated by the well drift.
```python
# (Assume build_well_mask is a helper function that maps well coordinates to cells)
well_mask = build_well_mask(centers, drifts)
```

### 5. Hydrate SSP&A Inputs
We package the heads, conductivity, porosity, and well mask into an `SspaInputs` object.
```python
# (Assume k and porosity are loaded or defined)
inputs = mp3du.hydrate_sspa_inputs(
    heads=heads,
    porosity=porosity,
    well_mask=well_mask,
    hhk=k,  # Note: hhk is an alias for hydraulic_conductivity
)
```

### 6. Fit the Velocity Field
We fit the SSP&A velocity field using the config, grid, inputs, and drifts.
```python
cfg = mp3du.SspaConfig(search_radius=300.0, krig_offset=0.1)
field = mp3du.fit_sspa(cfg, grid, inputs, drifts)
# grid is now consumed and cannot be reused
```

### 7. Run Simulations
We can now run simulations using the fitted velocity field.
```python
sim_cfg = mp3du.SimulationConfig.from_json(json.dumps({
    "velocity_method": "Waterloo",
    "solver": "DormandPrince",
    "adaptive": {"tolerance": 1e-6},
    "capture": {"max_time": 3650.0, "max_steps": 100000},
    "initial_dt": 0.1,
    "direction": 1.0,
}))
particles = [mp3du.ParticleStart(id=i, x=x, y=y, z=0.5, cell_id=cid, initial_dt=0.1)
             for i, (x, y, cid) in enumerate(starting_locations)]
results = mp3du.run_simulation(sim_cfg, field, particles)
```

### 8. Inspect Results
The results can be inspected or exported for visualization.
```python
for res in results:
    records = res.to_records()
    print(f"Particle {res.particle_id}: {res.final_status}, {len(records)} steps")
```

## Performance Notes
**Warning:** The `fit_sspa()` function uses kriging, which has an O(n²) computational cost (where n is the number of cells). For a 201×201 grid (40,401 cells), fitting takes approximately 350 seconds. Plan accordingly for large regional models.

## Full Validation Script
For a complete, runnable script that includes file I/O, dispersion, and result plotting, see `Examples/Example5a/02-MEUK_Equivalent/run_mp3du_rs.py` in the mod-PATH3DU repository. The simpler `run_simple.py` in the same directory provides a minimal version without dispersion.

## See Also
- [Tracking from Head Maps (SSP&A Workflow)](../guides/sspa-workflow.md)
- [SSP&A Velocity Interpolation](../concepts/sspa-velocity.md)
- [SSP&A Drift Schema](../reference/python-api/sspa-drift-schema.md)
- [SSP&A API Reference](../reference/python-api/index.md)
