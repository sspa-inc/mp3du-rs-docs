# Tracking from Head Maps (SSP&A Workflow)

## When to Choose SSP&A
The S.S. Papadopulos & Associates (SSP&A) method is ideal when you have a map of hydraulic heads (e.g., from a regional model or interpolated field data) but lack the detailed cell-by-cell flow budgets required by the Waterloo method. It provides a smooth, kriged velocity field that can be augmented with analytic elements (drifts) to represent local features like pumping wells.

## Required Inputs Checklist

| Input | Type | Shape | Notes |
|---|---|---|---|
| `grid` | `GridHandle` | N/A | The model geometry (passed to `fit_sspa()`). |
| `heads` | `np.ndarray[float64]` | `(N,)` | Hydraulic head for each cell. |
| `hydraulic_conductivity` or `hhk` | `np.ndarray[float64]` | `(N,)` | Hydraulic conductivity for each cell. Provide exactly one. |
| `porosity` | `np.ndarray[float64]` | `(N,)` | Porosity for each cell. |
| `well_mask` | `np.ndarray[bool]` | `(N,)` | Boolean array over cells indicating cells with wells. |
| `config` | `SspaConfig` | N/A | Fitting configuration (`search_radius`, `krig_offset`). |
| `drifts` | `list[dict]` | N/A | List of drift definitions (see [Drift Schema](../reference/python-api/sspa-drift-schema.md)). |

*Note: `N` is the total number of cells in the grid.*

## Step-by-Step Workflow

### 1. Build the Grid
First, create the model grid using `mp3du.build_grid()`. This requires defining the cell vertices and centers.

### 2. Prepare Input Arrays
Prepare the required 1D numpy arrays for heads, conductivity, porosity, and well_mask. Ensure they all have a length equal to the number of cells in the grid.

### 3. Hydrate SSP&A Inputs
Use `mp3du.hydrate_sspa_inputs()` to package the arrays into an `SspaInputs` object.

### 4. Define Drift Elements
Create a list of dictionaries defining any analytic elements (wells, line-sinks, no-flow boundaries) that should be superimposed on the velocity field.

### 5. Fit the Velocity Field
Call `mp3du.fit_sspa(config, grid, inputs, drifts)` with an `SspaConfig`, the grid, hydrated inputs, and drift list to generate the `VelocityFieldHandle`. Note: `well_mask` is part of the hydrated `SspaInputs`, not a separate argument.

### 6. Configure and Run Simulation
Create a `SimulationConfig`, define `ParticleStart` locations, and call `mp3du.run_simulation()` using the fitted velocity field.

!!! note "SimulationConfig velocity_method"
    Even when using the SSP&A method to fit the velocity field, the `velocity_method` in the `SimulationConfig` JSON must still be set to `"Waterloo"`. This is because `"Waterloo"` is currently the only supported velocity method in the configuration schema, and the underlying solver uses a unified interface for both field types.

### 7. Interpret Results

Each particle returns a `TrajectoryResult` with a `final_status`, a `termination_reason`, and a trajectory accessible via `to_records()`.

```python
for res in results:
    records = res.to_records()
    print(f"Particle {res.particle_id}: {res.final_status} — {len(records)} steps")
    if records:
        last = records[-1]
        print(f"  endpoint: ({last['x']:.2f}, {last['y']:.2f}) t={last['time']:.1f}")
```

| `final_status` | What it means | What to do |
|---|---|---|
| `CapturedByWell` | Particle reached a well within `capture_radius` | Expected for particles near pumping wells. |
| `CapturedAtModelEdge` | Particle hit a domain-boundary cell | Check if the boundary is realistic or if the grid is too small. |
| `Exited` | Particle left the grid entirely | Usually means the particle reached the edge of the model domain. |
| `MaxTime` | `capture.max_time` was reached | Increase `max_time` if particles haven't reached their destination. |
| `MaxSteps` | `capture.max_steps` was reached | Increase `max_steps`, or loosen `tolerance` to allow larger steps. |
| `Stagnated` | Velocity stayed below `stagnation_velocity` for `stagnation_limit` consecutive steps | Check for zero-head-gradient cells or dry cells in the head map. |
| `Error` | Solver failure (e.g. `max_rejects` exceeded) | See [Troubleshooting](troubleshooting.md). |

### 8. Visualise and Export

Plot pathlines over the head map to verify the results make physical sense:

```python
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(10, 8))

# Plot head contours (assumes heads is a 1D array over cells)
# For structured grids, reshape; for unstructured, use tricontourf
cx = np.array([c[0] for c in centers])
cy = np.array([c[1] for c in centers])
ax.tricontourf(cx, cy, heads, levels=20, cmap="Blues")
ax.tricontour(cx, cy, heads, levels=20, colors="grey", linewidths=0.3)

# Overlay particle pathlines
for res in results:
    recs = res.to_records()
    xs = [r["x"] for r in recs]
    ys = [r["y"] for r in recs]
    ax.plot(xs, ys, "r-", linewidth=0.5)
    ax.plot(xs[0], ys[0], "go", markersize=3)   # start
    ax.plot(xs[-1], ys[-1], "rs", markersize=3)  # end

ax.set_aspect("equal")
ax.set_title("SSP&A Particle Pathlines over Head Map")
plt.savefig("pathlines.png", dpi=150)
plt.show()
```

!!! tip "Sanity checks"
    - Pathlines should follow the head gradient (high → low for forward tracking).
    - Particles near wells should curve toward the well and terminate there.
    - If all particles show `MaxSteps` or `Stagnated`, the head field may be too flat or the fitting may have failed — check the head map for artefacts.

## Common Mistakes

### Passing Both conductivity Arguments
When calling `hydrate_sspa_inputs()`, you must provide either `hydraulic_conductivity` OR `hhk` (an alias for the same thing), but not both.

### Mismatched Array Lengths
All input arrays (heads, conductivity, porosity, well_mask) must have exactly the same length as the number of cells in the grid.

### well_mask Shape Confusion
The `well_mask` is a boolean array over cells (1D array covering all cells), not a list of well indices or coordinates.

### Reusing GridHandle After Fitting
The `GridHandle` is consumed by `fit_sspa()`. If you need to run multiple simulations or fit different fields, you must recreate the grid or clone it (if supported).

### Unsupported Drift Types
Ensure the `type` key in your drift dictionaries is one of the supported string values: `well`, `linesink` (or `line_sink`, `line-sink`), `noflow` (or `no_flow`, `no-flow`). Integer aliases are not supported.

### Zero-Length Line Segments
For `linesink` and `noflow` drifts, the start (`x1`, `y1`) and end (`x2`, `y2`) coordinates must not be identical.

### Expecting Line/NoFlow Capture
While line-sinks and no-flow boundaries influence the velocity field, particles will not currently be captured (terminated) or reflected by them. Only well capture is fully implemented.

### Underestimating Fitting Time
The SSP&A fitting process uses kriging, which has an O(n²) computational cost. For large grids, this step can take a significant amount of time.

## Diagnosing Silent Failures

A common experience when first running the MEUK/SSP&A workflow is that `fit_sspa()` completes (possibly after a long wait), `run_simulation()` returns results, but the output seems wrong — all particles stagnate, exit immediately, or produce nonsensical paths. Here is a diagnostic checklist:

### All particles show `MaxSteps` or `Stagnated`

1. **Head gradient is too flat.** If the head difference across the model is tiny relative to the cell size, velocities will be near-zero. Check `np.ptp(heads)` — if it's < 0.01 m across the domain, the gradient may be below numerical noise.
2. **Hydraulic conductivity is zero or very small.** Velocity = K × gradient / porosity. If K is orders of magnitude too small, particles won't move.
3. **`max_time` is too short.** For regional models with slow flow, particles may need millions of days. Check the expected travel time: `distance / (K * gradient / porosity)`.
4. **`stagnation_velocity` is too high.** If set to e.g. `1e-6` but actual velocities are `1e-8`, every step will count as stagnant. Lower it to `1e-14` or `0.0` to disable stagnation detection while debugging.

### All particles show `Exited` immediately

1. **Starting coordinates are outside the grid.** Verify that each `ParticleStart(x, y)` falls inside the polygon of `cell_id`. Use a point-in-polygon check.
2. **`cell_id` is wrong.** Cell IDs are 0-based. If your particle-start file uses 1-based IDs, subtract 1.
3. **`z` is out of range.** The local z coordinate should be between 0.0 (cell bottom) and 1.0 (cell top). A value like `z=50.0` (an elevation) will cause immediate exit.

### `fit_sspa()` takes a very long time then results look wrong

1. **`search_radius` is too small.** If the search radius doesn't reach enough neighbouring cells, the kriging system is under-determined and produces noisy velocities. Try doubling it.
2. **`search_radius` is too large.** If it covers the entire domain, the kriging system is huge and slow, and may produce over-smoothed velocities. `search_radius` only needs to span a few raster cells — **2–3× the cell size** of the input raster is the recommended starting point. Read the cell size dynamically (e.g. `rasterio.open("heads.tif").res[0]`) rather than hard-coding a value.
3. **Well drifts are missing or have wrong coordinates.** If wells are present in the head map but not in the drift list, the kriging will try to fit the well drawdown cone with smooth polynomials, producing artefacts.
4. **`well_mask` doesn't cover the well cells.** The mask tells the fitter to skip cells dominated by well drawdown. If it's all-False, the fitter will try to fit through the well cone.

### Particles curve the wrong way

1. **`direction` is wrong.** Forward tracking (`1.0`) follows flow from high head to low head. Backward tracking (`-1.0`) goes upgradient. If your particles go the wrong way, flip the sign.
2. **Well `value` sign is wrong.** Pumping wells should have negative `value` (extraction). Injection wells should have positive `value`.

## Next Steps
- [SSP&A: Particle Tracking from Water Level Maps](../examples/sspa-water-level.md)
- [SSP&A Velocity Interpolation](../concepts/sspa-velocity.md)
- [SSP&A API Reference](../reference/python-api/index.md)
