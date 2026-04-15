# MEUK Example (SSP&A)

This example demonstrates a complete workflow for tracking particles from a regional water level map using the SSP&A (S.S. Papadopulos & Associates) kriging-based velocity engine. It replicates the MEUK model (Modèle d'Écoulement des eaux souterraines de l'Université de Kinshasa) from the original mod-PATH3DU distribution.

## Model Description

- **Grid**: 201×201 structured grid (100 m cells), single layer.
- **Hydraulic conductivity**: 100 m/d (constant).
- **Porosity**: 0.3 (constant).
- **Heads**: Kriged heads loaded from an ASC raster.
- **Wells**: Three extraction wells loaded from a CSV file.
- **Particles**: 144 particles starting from locations defined in a shapefile.
- **Simulations**: Three endpoint simulations at 5044, 23363, and 50000 days.

## Running the Examples

The scripts for this example are not self-contained downloads. They depend on external model data files (`mp3du.gsf`, `Heads_for_MEUK.asc`, `MEUK_WELLS.csv`, `PartStart_Intersect.*`) from `Examples/Example5a/02-MEUK_Equivalent/` in the mod-PATH3DU repository. The validation workflow also depends on legacy reference shapefiles in `Examples/Example5a/Shapefiles/`.

To run these scripts, you must execute them from within that directory:

```bash
cd Examples/Example5a/02-MEUK_Equivalent/
python meuk_tutorial_smoke_test.py
python meuk_validation_workflow.py
```

## 1. Tutorial Script (`meuk_tutorial_smoke_test.py`)

This is a minimal "smoke test" or tutorial script. It runs one particle per release location with **no dispersion** and **no repeats**. It focuses purely on the core SSP&A workflow: loading the grid, heads, and wells, fitting the velocity field, running the simulation, and plotting the pathlines. It still requires the external Example 5a input files listed above.

### Output

The tutorial script writes `meuk_tutorial_smoke_test_plot.png` to the working
example directory when run locally. The image is not bundled into the published
docs site because it is generated from external Example 5a input files.

### Code

```python
--8<-- "docs/examples/sspa-meuk-example/meuk_tutorial_smoke_test.py"
```

## 2. Validation Script (`meuk_validation_workflow.py`)

This is a full validation script. It includes dispersion, runs Monte Carlo repeats (e.g., 100 to 5000 times per particle), bins the endpoints into a concentration grid, loads the legacy C++ reference shapefiles, and computes quantitative validation metrics (Pearson correlation, normalized RMSE, mass error) to prove the Rust engine matches the legacy C++ engine. Besides the Example 5a input files, it also requires the reference shapefiles from `Examples/Example5a/Shapefiles/`.

### Output

The validation script writes `meuk_validation_workflow_head_plot.png` to the
working example directory when run locally. The image is not bundled into the
published docs site because it is generated from external Example 5a input files
and legacy reference shapefiles.

### Code

```python
--8<-- "docs/examples/sspa-meuk-example/meuk_validation_workflow.py"
```

## See Also

- [Tracking from Head Maps (SSP&A Workflow)](../guides/sspa-workflow.md)
- [SSP&A Velocity Interpolation](../concepts/sspa-velocity.md)
- [SSP&A Drift Schema](../reference/python-api/sspa-drift-schema.md)
- [SSP&A API Reference](../reference/python-api/index.md)
