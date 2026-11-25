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

The scripts for this example are not self-contained downloads. They depend on external model data files (`mp3du.gsf`, `Heads_for_MEUK.asc`, `MEUK_WELLS.csv`, `PartStart_Intersect.*`) from `Examples/Example5a/02-MEUK_Equivalent/` in the mod-PATH3DU repository. The validation workflow also depends on the MODFLOW heads file `Examples/Example5a/01-MODFLOW/dispdemoWEL.hds`, and on the mod-PATH3DU reference concentrations [`meuk_reference_concentrations.csv`](sspa-meuk-example/meuk_reference_concentrations.csv), which must be downloaded into the same directory as the script.

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

This is a full validation script. It tracks the particles with GSDE dispersion, runs Monte Carlo repeats (e.g., 100 to 5000 times per particle), and bins the endpoints of the particles that are still in the aquifer at the end time. Particles captured by the wells are not counted, as in the mod-PATH3DU reference. The script converts the counts to concentrations the same way the reference was made (count × mass per particle ÷ pore volume, with the pore volume taken from the MODFLOW heads) and compares the two concentration grids. It reports the fraction of particles still in the aquifer, the Pearson correlation and the normalized RMSE of the concentrations, and the difference in the mass remaining in the aquifer (the sum of concentration × pore volume, MP3DU-RS relative to mod-PATH3DU).

Each end time is run with two tracking set-ups, which `MP3DU_SETUPS` selects (both by default):

- `cpp_input`: as the mod-PATH3DU input `Ex4_MEUK.json` (step-doubling Runge-Kutta, no practical step limit), so that the comparison with the reference is like for like;
- `dopri_1000`: Dormand-Prince with a 1,000-day step limit.

The script gives the dispersivities in the configuration's `dispersion` block, as `Ex4_MEUK.json` gives them in its `DISPERSION` block: `alpha_l` 100 m (`LONGITUDINAL`), `alpha_th` 10 m (`TRANSVERSE_HORIZONTAL`) and `alpha_tv` 0, which an SSP&A field requires. It passes no dispersivity arrays to `hydrate_sspa_inputs()`; see [Giving the Dispersivities](../reference/dispersion-methods.md#giving-the-dispersivities).

The reference concentrations were made with mod-PATH3DU 2.1.9 (November 2026 build, which has the GSDE dispersion of LaBolle et al., 2000) from `Ex4_MEUK.json` as published, with 5,000 repeats per particle. The first lines of the file record how it was made.

### Output

The validation script writes `meuk_validation_workflow_head_plot.png` and, for
each set-up and end time, `validation_<set-up>_<simulation>.png` (reference,
MP3DU-RS and difference maps) to the working example directory when run locally.
The images are not bundled into the published docs site because they are
generated from external Example 5a input files.

### Code

```python
--8<-- "docs/examples/sspa-meuk-example/meuk_validation_workflow.py"
```

## What to Do After the Script Runs

### Quick Health Check

After either script finishes, run this diagnostic snippet to understand what happened:

```python
from collections import Counter

status_counts = Counter(r.final_status for r in results)
print("=== Particle Status Summary ===")
for status, count in status_counts.most_common():
    print(f"  {status}: {count}")

# Check if any particles actually moved
for res in results[:3]:  # inspect first 3
    recs = res.to_records()
    if recs:
        first, last = recs[0], recs[-1]
        dist = ((last["x"] - first["x"])**2 + (last["y"] - first["y"])**2)**0.5
        print(f"  Particle {res.particle_id}: {res.final_status}, "
              f"moved {dist:.1f} m in {last['time']:.1f} days, {len(recs)} steps")
```

### Expected Outcomes

For the **tutorial smoke test** (no dispersion, 1 realisation per particle):

- Most particles should show `CapturedByWell`, `CapturedAtModelEdge`, or `ExitedDomain`.
- Pathlines should follow the head gradient and curve toward the three extraction wells.
- If all particles hit the step limit (`TimeLimitReached`) or show `Stagnated`, see the troubleshooting section below.

For the **validation workflow** (with dispersion, Monte Carlo repeats):

- Each particle is run many times (100–5000 realisations) with random dispersion, for each tracking set-up.
- The endpoints of the particles still in the aquifer are binned into a concentration grid and compared against the mod-PATH3DU reference. Particles captured by the wells are excluded, as in the reference, so both grids show the mass remaining in the aquifer.

The fraction of particles still in the aquifer, with MP3DU-RS 0.1.7 at 1,000 repeats (144,000 particles):

| | 5,044 days | 23,363 days | 50,000 days |
|---|---|---|---|
| mod-PATH3DU 2.1.9 (reference, 5,000 repeats) | 1.000 | 0.950 | 0.0252 |
| MP3DU-RS 0.1.7, `cpp_input` | 1.000 | 0.940 | 0.0292 |
| MP3DU-RS 0.1.7, `dopri_1000` | 1.000 | 0.940 | 0.0295 |
| MT3D | — | 0.944 | 0.029 |

The Pearson correlation and the normalised RMSE of the concentrations against the reference, at 1,000 repeats:

| Set-up | 5,044 days | 23,363 days | 50,000 days |
|---|---|---|---|
| `cpp_input` | 0.999, 0.001 | 0.995, 0.006 | 0.89, 0.021 |
| `dopri_1000` | 0.999, 0.001 | 0.995, 0.006 | 0.90, 0.021 |

Since 0.1.7 MP3DU-RS does not agree with the mod-PATH3DU reference in the mass left in the aquifer: about 1% less at 23,363 days and 16% (`cpp_input`) to 17% (`dopri_1000`) more at 50,000 days, well beyond the Monte Carlo noise (about 2% at 50,000 days). The concentrations are distributed alike (the correlations above). The difference comes from the order of the two parts of a step with dispersion: 0.1.7 makes the dispersive displacement first and follows the advection from where the particle lands, mod-PATH3DU takes the advection from where the step starts. MP3DU-RS 0.1.5 and 0.1.6, which did the same as mod-PATH3DU, agreed with it within the noise (0.951 and 0.0257 at 500 repeats with `cpp_input`). Against MT3D, 0.1.7 is about as far below at 23,363 days as mod-PATH3DU is above, and closer at 50,000 days; its result also changes little with the step size (0.942 with a `max_dt` of 250 or 62.5 days; see [Step Size](../concepts/dispersion-theory.md#step-size)). MT3D has errors of its own, and neither particle code has been shown to converge on this model. The correlation at the late times rises with the number of repeats: at 50,000 days only about 3% of the particles remain in the aquifer, so the binned concentrations are noisy unless the number of repeats is large.

!!! note "Earlier versions of this comparison"
    Before MP3DU-RS 0.1.5 this page compared with reference shapefiles made in 2018, before mod-PATH3DU's dispersion was corrected in November 2026, and reported about 35% less mass in the aquifer at 50,000 days. That difference came from the reference, which lacked the dispersive drift and left 0.043 of the particles in the aquifer.

### Common Problems

| Symptom | Likely Cause | Fix |
|---|---|---|
| All particles `Stagnated` | Head field is flat or K is too small | Check `np.ptp(heads)` and K values |
| All particles `TimeLimitReached` at the step limit | `max_steps` too low or `tolerance` too tight | Increase `max_steps` to 1,000,000+ or loosen `tolerance` to 1e-5 |
| All particles `ExitedDomain` immediately | Starting coordinates outside grid or wrong `cell_id` | Verify particle starts fall inside their assigned cells |
| `fit_sspa()` hangs for hours | Grid is very large (> 50k cells) | Expected — kriging is O(n²). For 40k cells, ~350 s is normal |
| Pathlines go the wrong direction | `direction` is `-1.0` instead of `1.0` | Use `1.0` for forward (downgradient) tracking |
| Particles ignore wells | Well drifts missing or `well_mask` is all-False | Ensure drifts list includes all wells and `well_mask[cell]` is True for well cells |
| Validation metrics are poor | Different dispersion settings, too few Monte Carlo repeats, or an old reference file | Use the `cpp_input` set-up and at least 500 repeats; download the current `meuk_reference_concentrations.csv` |

For a comprehensive diagnostic guide, see [SSP&A Workflow — Diagnosing Silent Failures](../guides/sspa-workflow.md#diagnosing-silent-failures).

## See Also

- [Tracking from Head Maps (SSP&A Workflow)](../guides/sspa-workflow.md)
- [SSP&A Velocity Interpolation](../concepts/sspa-velocity.md)
- [SSP&A Drift Schema](../reference/python-api/sspa-drift-schema.md)
- [SSP&A API Reference](../reference/python-api/index.md)
