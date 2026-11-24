# Troubleshooting

Common problems and their solutions.

## Installation Issues

### `ModuleNotFoundError: No module named 'mp3du'`

**Cause:** The `mp3du` package is not installed in the active Python environment.

**Solution:**

Install the wheel directly from the [GitHub Releases page](https://github.com/sspa-inc/mp3du-rs/releases):

```bash
pip install https://github.com/sspa-inc/mp3du-rs/releases/download/vX.Y.Z/mp3du_py-X.Y.Z-cp38-abi3-win_amd64.whl
```

Replace the URL with the actual link to the latest `.whl` asset. See the [Installation guide](../getting-started/install.md) for full instructions.

!!! tip
    Verify you are in the correct virtual environment:

    ```bash
    # Windows
    .venv\Scripts\activate
    pip list | findstr mp3du

    # macOS / Linux
    source .venv/bin/activate
    pip list | grep mp3du
    ```

## Configuration Errors

### `Invalid solver name`

**Error pattern:** `unknown variant 'dormandprince', expected one of 'Euler', 'Rk4StepDoubling', ...`

**Cause:** Solver names are case-sensitive enums. Lowercase or underscore-separated names are not accepted.

**Solution:** Use the exact enum value:

```json
"solver": "DormandPrince"
```

Valid values: `Euler`, `Rk4StepDoubling`, `DormandPrince`, `CashKarp`, `VernerRobust`, `VernerEfficient`.

See [Solver Methods](../reference/solver-methods.md) for all solver options.

### Schema validation failures

**Error pattern:** `jsonschema.ValidationError: 'xyz' is not valid under any of the given schemas`

**Cause:** The configuration JSON does not conform to the schema. Common sub-causes:

- Missing required fields
- Extra fields (the schema sets `additionalProperties: false`; since 0.1.4 `SimulationConfig.from_json()` rejects them too, with ``unknown field `{key}` ``)
- Wrong types (e.g., the string `"1.0"` instead of the number `1.0` for `direction`)

**Solution:** Validate against the schema to get a specific error message:

```python
import json
import urllib.request
import jsonschema

schema_url = "https://sspa-inc.github.io/mp3du-rs-docs/assets/raw/mp3du_schema.json"
with urllib.request.urlopen(schema_url) as response:
    schema = json.load(response)
with open("my_config.json") as f:
    config = json.load(f)

try:
    jsonschema.validate(instance=config, schema=schema)
except jsonschema.ValidationError as e:
    print(f"Path: {'.'.join(str(p) for p in e.absolute_path)}")
    print(f"Error: {e.message}")
```

See [Schema Reference](../reference/schema-reference.md) for field specifications and [Building Configs](building-configs.md) for common mistakes.

### `direction` must be `1.0` or `-1.0`

**Error pattern:** `direction must be 1.0 (forward) or -1.0 (backward)` (from `from_json()`), or `0.5 is not one of [1.0, -1.0]` (from `jsonschema`)

**Cause:** The `direction` field is not one of the two allowed values; it is not a speed or a range. Writing `1` or `-1` as an integer is accepted, since these are the same values.

**Solution:**

```json
"direction": 1.0
```

### Unknown field in the configuration

**Error pattern:** ``unknown field `capture_raduis`, expected one of `max_time`, `max_steps`, ...``

**Cause:** The configuration contains a key it does not have, usually a misspelling. Since 0.1.4 this is an error; before, such a key was ignored, so a misspelled optional setting fell back to its default without notice.

**Solution:** Correct or remove the key. The message lists the keys accepted at that level of the configuration.

### Dispersivity given twice, or not at all

**Error pattern:** `config error: dispersivity is given twice: ...` or `config error: dispersion is on but no dispersivity is given. ...`, from `run_simulation()`.

**Cause:** The dispersivities come from exactly one place: the per-cell arrays `disp_long`, `disp_trans_h` and `disp_trans_v` given to `hydrate_cell_properties()` or `hydrate_sspa_inputs()`, or `alpha_l`, `alpha_th` and `alpha_tv` in the `dispersion` block. Scripts written for 0.1.5 or earlier give both, because the arrays were required.

**Solution:** Remove one of the two. To keep the results of 0.1.5, which used the configuration's values, leave the arrays out. The other dispersivity errors are listed in [Dispersivity Errors](../reference/error-diagnostics.md#dispersivity-errors).

## Runtime Errors

### Particle outside grid

**Error pattern:** `particle exited domain at step N` or `final_status = "ExitedDomain"`

**Cause:** The particle's starting coordinates are outside the specified cell, or the particle naturally exits the model domain during tracking.

**Solution:**

- Verify starting coordinates: ensure $(x, y, z)$ is inside the polygon of `cell_id` and between the cell's top and bottom elevations
- If particles are exiting unexpectedly, check that the flow field is correctly loaded and the grid boundary conditions are as expected

### Simulation hangs or is very slow

**Cause:** Several possibilities:

- **Tolerance too tight:** Very small `tolerance` values cause many rejected steps and tiny step sizes
- **Pathological velocity field:** Near-zero or oscillating velocities in some cells
- **`min_dt` too small:** Allows the solver to take extremely small steps instead of failing

**Solution:**

1. Start with the default tolerance (`1e-6`) and DormandPrince solver
2. Check for cells with near-zero velocity — these may indicate dry cells or data issues
3. Set `min_dt` to a reasonable floor (e.g., `1e-10`) to prevent the solver from stalling, and set `euler_dt` equal to it
4. Enable stagnation detection with `stagnation_velocity` and `stagnation_limit`

!!! tip
    Start with default settings and gradually adjust. If a simulation takes longer than expected, reduce `max_steps` temporarily to diagnose the issue quickly.

### `max_rejects exceeded`

**Error pattern:** `final_status = "SolverFailed"` with step size rejection

**Cause:** The solver cannot find a step size that satisfies the tolerance. This usually happens in regions with discontinuous or extremely steep velocity gradients.

**Solution:**

- Increase `max_rejects` (e.g., from 10 to 50)
- Loosen `tolerance` (e.g., from `1e-8` to `1e-6`)
- Lower `min_scale` to allow more aggressive step reduction
- Check the velocity field for discontinuities near the particle location

## Data Issues

### Array dimension mismatch

**Error pattern:** `Array '{name}' has length N, expected M` during hydration

**Cause:** One or more NumPy arrays passed to `hydrate_cell_properties()` or `hydrate_cell_flows()` has the wrong length.

**Solution:**

```python
n = grid.n_cells()
assert top.shape == (n,), f"top: expected ({n},), got {top.shape}"
assert bot.shape == (n,), f"bot: expected ({n},), got {bot.shape}"
# ... check all arrays
```

All per-cell arrays must have shape `(n_cells,)`. Face arrays (`face_flow`, `face_neighbor`) must have shape `(n_faces,)`, and `face_offset` must have shape `(n_cells + 1,)`.

### Non-contiguous array error

**Error pattern:** `Array '{name}' must be a contiguous 1D numpy.float64 array`

**Cause:** Float and bool arrays passed to hydration functions must be C-contiguous. Transposed or sliced arrays may not be. (The integer arrays need not be.)

**Solution:**

```python
array = np.ascontiguousarray(array)
```

### Wrong array dtype

**Error pattern:** `TypeError: argument 'head': expected a 1-D NumPy array of dtype float64, got a 1-D array of dtype int64; ...`

**Cause:** Float arrays must be `float64` and masks `bool`; an array built from integers (`np.array([10, 20])`) or with `float32` values is rejected. The integer arrays (`face_offset`, `face_neighbor` and the `bc_*` ids and codes) accept any integer dtype.

**Solution:** Convert as the message says:

```python
head = np.asarray(head, dtype="float64")
has_well = np.asarray(has_well, dtype=bool)
```

See [Error Diagnostics](../reference/error-diagnostics.md#wrong-array-type-or-dtype).

### NaN or Inf in results

**Cause:** Numerical issues in the velocity field, typically from:

- Division by zero in cells with zero porosity or zero area
- Extremely large velocity gradients
- Incorrect input data (e.g., top elevation below bottom elevation)

**Solution:**

- Check input arrays for NaN/Inf: `assert np.all(np.isfinite(array))`
- Verify `top > bot` for all cells
- Verify `porosity > 0` for all cells
- Check for cells with zero area or zero perimeter

## Getting Help

When reporting an issue, include:

1. **mod-PATH3DU version:** `python -c "import mp3du; print(mp3du.version())"`
2. **Python version:** `python --version`
3. **Platform:** Windows, macOS, or Linux
4. **Exact error text** (full traceback if available)
5. **Configuration JSON** (or minimal reproducing config)
6. **Grid dimensions:** number of cells, number of faces

## Boundary Capture Issues

### Particles pass through CHD cells without being captured

**Cause:** No boundary data was provided to `hydrate_cell_flows()`, or the IFACE value is wrong.

**Solution:** Pass the `bc_*` arrays to `hydrate_cell_flows()` with the correct IFACE mapping for each BC package:

| BC Package | Typical IFACE |
|-----------|--------------|
| WEL | 0 (well at cell centre) |
| CHD | 2 (side face) |
| RCH | 6 (top face) |
| EVT | 6 (top face) |
| DRN | 6 (top face) |
| GHB | 2 (side face) |

See [IFACE & Boundary Capture](../concepts/iface-boundary-capture.md) for the full IFACE reference.

### Particles captured as `CapturedByWell` when they should be `CapturedByBoundary`

**Cause:** The legacy `has_well=True` workaround is still set for non-well BC cells (e.g., CHD cells marked as wells to force capture).

**Solution:** Remove the `has_well` workaround. Instead, pass the proper `bc_*` arrays with the correct IFACE values. When boundary entries exist for a cell, `has_well` is ignored.

### Particles terminated as `CapturedAtModelEdge` instead of well capture

**Cause:** `is_domain_boundary=True` is set for a cell that contains an IFACE 0 (well) entry. Domain-boundary capture has the highest priority and overrides well capture.

**Solution:** Do not set `is_domain_boundary=True` for cells with IFACE 0 wells. The C++ implementation excludes IFACE 0 cells from domain-boundary capture.

### Unexpected `termination_reason` for IFACE 7 cells

**Cause:** IFACE 7 routes flow to `q_top` (with negation) for the velocity field, but uses the `INTERNAL` capture classification — not `TopFace`.

**Solution:** This is the intended behaviour. IFACE 7 represents an internal BC without a specific well, so capture triggers immediately on cell entry (like IFACE 2), but the flow contribution goes to `q_top` for velocity reconstruction. The `termination_reason` will show the BC type name.

## See Also

- [Error Diagnostics](../reference/error-diagnostics.md) — Full error catalog with all known error patterns
- [Building Configs](building-configs.md) — Configuration guide and common mistakes
- [Units & Conventions](../reference/units-and-conventions.md) — Ensure consistent units across all inputs
