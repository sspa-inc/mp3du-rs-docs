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

## Next Steps
- [SSP&A: Particle Tracking from Water Level Maps](../examples/sspa-water-level.md)
- [SSP&A Velocity Interpolation](../concepts/sspa-velocity.md)
- [SSP&A API Reference](../reference/python-api/index.md)
