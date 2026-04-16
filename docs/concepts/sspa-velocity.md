# SSP&A Velocity Interpolation (Tracking from Head Maps)

## What is SSP&A?
The S.S. Papadopulos & Associates (SSP&A) method is a technique for interpolating a continuous velocity field directly from a map of hydraulic heads (water level maps). Unlike the Waterloo method, which reconstructs velocities from cell-by-cell flow budgets, the SSP&A method uses kriging to fit a smooth velocity surface to the observed or simulated head gradients.

## SSP&A vs Waterloo: When to Use Each

| Feature | Waterloo Method | SSP&A Method |
|---|---|---|
| **Primary Input** | Cell-by-cell flow budgets (e.g., MODFLOW `.cbb`) | Hydraulic head maps (e.g., MODFLOW `.hds` or interpolated rasters) |
| **Velocity Field** | Piecewise continuous, mass-conserving | Smooth, kriged surface |
| **Best For** | Standard groundwater models with full flow budgets | Regional models where only head maps are available, or when a smoother velocity field is desired |
| **Performance** | Fast, local reconstruction | Slower, O(n²) global fitting |

## How SSP&A Works
The SSP&A method works by:
1. Calculating local hydraulic gradients from the provided head map.
2. Using Darcy's law (with the provided hydraulic conductivity and porosity) to estimate local velocities at cell centers.
3. Fitting a global velocity field using kriging to interpolate these local estimates into a continuous surface.
4. Superimposing analytic elements ("drifts") to represent local features like pumping wells or rivers that might not be fully captured by the regional head map.

## Required Inputs
To use the SSP&A method, you need the following inputs:
- [x] **Grid**: A `GridHandle` representing the model geometry (passed to `fit_sspa()`).
- [x] **Heads**: A 1D numpy array of hydraulic heads per cell, shape `(n_cells,)`.
- [x] **Hydraulic Conductivity**: A 1D numpy array of hydraulic conductivity per cell, shape `(n_cells,)`. Pass as `hydraulic_conductivity=` or `hhk=` (exactly one).
- [x] **Porosity**: A 1D numpy array of porosity per cell, shape `(n_cells,)`.
- [x] **Well Mask**: A boolean array over cells indicating which cells contain wells, shape `(n_cells,)`.
- [x] **Drifts**: A list of dictionaries defining the analytic elements (wells, line-sinks, no-flow boundaries). See the [SSP&A Drift Schema](../reference/python-api/sspa-drift-schema.md).
- [x] **SspaConfig**: Configuration object specifying `search_radius` and `krig_offset`. The `search_radius` only needs to span a few raster cells — set it to **2–3× the cell size** of the input raster. Best practice is to read the cell size from each raster (e.g. via `rasterio`) and compute `search_radius` dynamically rather than hard-coding a value.

## Understanding well_mask
The `well_mask` is a boolean array over cells with the same length as the number of cells in the grid. It is *not* a list of well locations. Instead, it acts as a flag for the kriging algorithm. Cells where `well_mask` is `True` are excluded from the background velocity interpolation, as their local gradients are assumed to be dominated by the well (which will be handled separately by a drift element).

## Understanding Drifts
Drifts are analytic elements superimposed on the kriged background velocity field. They allow you to explicitly represent features that strongly influence local flow but might be smoothed out in the regional head map. Supported drift types include:
- **Wells**: Point sinks or sources.
- **Line-Sinks**: Line segments representing rivers or drains.
- **No-Flow**: Line segments representing impermeable boundaries.

## Known Limitations

### O(n²) Fitting Cost
The kriging process used to fit the SSP&A velocity field has an O(n²) computational complexity, where n is the number of cells. This means that fitting the field can be significantly slower than the Waterloo method, especially for large models.

### Performance Feature: On-Demand Cell Setup
Even though SSP&A has an expensive neighborhood-building step up front, mod-PATH3DU does **not** fully prepare every cell before tracking starts. Instead, it finishes the heavier per-cell setup only when a particle actually needs velocity in that cell. In practice, this means you only pay the full per-cell cost for cells that particles actually visit.

### Line-Sink / No-Flow Capture Not Yet Implemented
While line-sinks and no-flow boundaries influence the interpolated velocity field, explicit particle capture (termination) at line-sinks or reflection at no-flow boundaries is not yet implemented in the tracking engine. Currently, only well capture is fully supported.

## Validation Rules and Error Cases
The `fit_sspa()` function performs strict validation on the inputs. Common errors include:
- **Mismatched Array Lengths**: All input arrays (heads, conductivity, porosity, etc.) must have the same length as the number of cells in the grid.
- **Invalid Drift Definitions**: Drifts must follow the required schema. See the [SSP&A Drift Schema](../reference/python-api/sspa-drift-schema.md) for details.

## Next Steps
- [Tracking from Head Maps (SSP&A Workflow)](../guides/sspa-workflow.md)
- [SSP&A: Particle Tracking from Water Level Maps](../examples/sspa-water-level.md)
- [SSP&A API Reference](../reference/python-api/index.md)
