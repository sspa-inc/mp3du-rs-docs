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
# search_radius should be 2–3× the raster cell size — read it dynamically:
#   import rasterio; cell_size = rasterio.open("heads.tif").res[0]
#   search_radius = 2.0 * cell_size
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
`search_radius` should be 2–3× the raster cell size — read it dynamically rather than hard-coding.
```python
# Best practice: derive search_radius from the raster cell size
# import rasterio; cell_size = rasterio.open("heads.tif").res[0]
# search_radius = 2.0 * cell_size
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

### 9. Understand What Happened

After `run_simulation()` returns, every particle has a `final_status` that tells you
why it stopped. This is the single most important thing to check:

```python
from collections import Counter
status_counts = Counter(r.final_status for r in results)
for status, count in status_counts.most_common():
    print(f"  {status}: {count}")
```

| `final_status` | Meaning | Action |
|---|---|---|
| `CapturedByWell` | Reached a well within `capture_radius` | ✅ Expected near pumping wells |
| `CapturedAtModelEdge` | Hit a domain-boundary cell | Check if the boundary is realistic |
| `Exited` | Left the grid entirely | Normal at model edges; unexpected in the interior |
| `MaxTime` | Ran out of simulation time | Increase `capture.max_time` |
| `MaxSteps` | Ran out of integration steps | Increase `capture.max_steps` or loosen `adaptive.tolerance` |
| `Stagnated` | Velocity too low for too long | Lower `stagnation_velocity` or check head field |
| `Error` | Solver failure | See [Troubleshooting](../guides/troubleshooting.md) |

!!! warning "If most particles show `MaxSteps` or `Stagnated`"
    This usually means the velocity field is near-zero everywhere. Check:

    1. `np.ptp(heads)` — is the head range realistic? A flat head field produces no flow.
    2. Hydraulic conductivity values — are they in the right units and magnitude?
    3. `stagnation_velocity` — if set too high (e.g. `1e-6`), slow but valid flow will be flagged as stagnant. Try `1e-14` while debugging.
    4. `max_time` — for regional models with slow flow, particles may need millions of days.

### 10. Plot Pathlines

A quick visual check is the best way to verify results:

```python
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(10, 8))
cx = np.array([c[0] for c in centers])
cy = np.array([c[1] for c in centers])
ax.tricontourf(cx, cy, heads, levels=20, cmap="Blues")
ax.tricontour(cx, cy, heads, levels=20, colors="grey", linewidths=0.3)

for res in results:
    recs = res.to_records()
    xs = [r["x"] for r in recs]
    ys = [r["y"] for r in recs]
    ax.plot(xs, ys, "r-", linewidth=0.5)
    ax.plot(xs[0], ys[0], "go", markersize=3)
    ax.plot(xs[-1], ys[-1], "rs", markersize=3)

ax.set_aspect("equal")
ax.set_title("SSP&A Pathlines")
plt.savefig("pathlines.png", dpi=150)
plt.show()
```

Pathlines should follow the head gradient (high → low for forward tracking) and curve toward wells.

## Performance Notes
**Warning:** The `fit_sspa()` function uses kriging, which has an O(n²) computational cost (where n is the number of cells). For a 201×201 grid (40,401 cells), fitting takes approximately 350 seconds. Plan accordingly for large regional models.

## Troubleshooting

See the [SSP&A Workflow — Diagnosing Silent Failures](../guides/sspa-workflow.md#diagnosing-silent-failures) section for a comprehensive checklist covering:

- All particles stagnating or hitting `MaxSteps`
- Particles exiting immediately
- `fit_sspa()` producing wrong velocities
- Particles curving the wrong direction

## Full Validation Script
For a complete, runnable script that includes file I/O, dispersion, and result plotting, see the [MEUK Example (SSP&A)](sspa-meuk-example.md) example.

## See Also
- [Tracking from Head Maps (SSP&A Workflow)](../guides/sspa-workflow.md)
- [SSP&A Velocity Interpolation](../concepts/sspa-velocity.md)
- [SSP&A Drift Schema](../reference/python-api/sspa-drift-schema.md)
- [SSP&A API Reference](../reference/python-api/index.md)

