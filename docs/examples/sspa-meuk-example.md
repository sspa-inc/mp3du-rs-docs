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

The scripts for this example require data files (`mp3du.gsf`, `Heads_for_MEUK.asc`, `MEUK_WELLS.csv`, `PartStart_Intersect.*`) that are located in the `Examples/Example5a/02-MEUK_Equivalent/` directory of the mod-PATH3DU repository.

To run these scripts, you must execute them from within that directory:

```bash
cd Examples/Example5a/02-MEUK_Equivalent/
python run_simple.py
python run_mp3du_rs.py
```

## 1. Tutorial Script (`run_simple.py`)

This is a minimal "smoke test" or tutorial script. It runs one particle per release location with **no dispersion** and **no repeats**. It focuses purely on the core SSP&A workflow: loading the grid, heads, and wells, fitting the velocity field, running the simulation, and plotting the pathlines.

### Output

![Simple Run Plot](../../assets/images/run_simple_plot.png)

### Code

```python
--8<-- "docs/examples/sspa-meuk-example/run_simple.py"
```

## 2. Validation Script (`run_mp3du_rs.py`)

This is a full validation script. It includes dispersion, runs Monte Carlo repeats (e.g., 100 to 5000 times per particle), bins the endpoints into a concentration grid, loads the legacy C++ reference shapefiles, and computes quantitative validation metrics (Pearson correlation, normalized RMSE, mass error) to prove the Rust engine matches the legacy C++ engine.

### Output

![Validation Head Plot](../../assets/images/run_mp3du_rs_head_plot.png)

### Code

```python
--8<-- "docs/examples/sspa-meuk-example/run_mp3du_rs.py"
```

## See Also

- [Tracking from Head Maps (SSP&A Workflow)](../guides/sspa-workflow.md)
- [SSP&A Velocity Interpolation](../concepts/sspa-velocity.md)
- [SSP&A Drift Schema](../reference/python-api/sspa-drift-schema.md)
- [SSP&A API Reference](../reference/python-api/index.md)
