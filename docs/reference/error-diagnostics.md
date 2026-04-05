# Error Diagnostics

Catalog of known error conditions in mod-PATH3DU. All errors surface as Python `ValueError` exceptions with descriptive messages.

!!! info "Initial Version"
    This catalog is initially hand-authored from codebase knowledge. Each error lists the exact or templated message text, cause, and remedy.

---

## Configuration Errors

Raised during `SimulationConfig.from_json()` or `SimulationConfig.validate()`.

### Invalid JSON syntax

!!! danger "Error"
    `expected value at line {line} column {col}`

**Cause:** The JSON string passed to `SimulationConfig.from_json()` is not valid JSON (missing commas, unclosed braces, trailing commas, etc.).

**Remedy:** Validate the JSON with a linter or `json.loads()` before passing to `from_json()`.

### Invalid solver name

!!! danger "Error"
    `unknown variant "{value}", expected one of "Euler", "Rk4StepDoubling", "DormandPrince", "CashKarp", "VernerRobust", "VernerEfficient"`

**Cause:** The `solver` field in the configuration JSON contains an unrecognized string value.

**Remedy:** Use one of the exact solver names: `"Euler"`, `"Rk4StepDoubling"`, `"DormandPrince"`, `"CashKarp"`, `"VernerRobust"`, `"VernerEfficient"`.

### Invalid dispersion method

!!! danger "Error"
    `data did not match any variant of untagged enum`

**Cause:** The `dispersion` object does not match any of the three valid schemas (`"None"`, `"Gsde"`, or `"Ito"`). Common causes: missing `method` field, misspelled method name, or missing required dispersivity parameters.

**Remedy:** Ensure the `dispersion` object includes a valid `method` field and all required parameters. See [Dispersion Methods](dispersion-methods.md) for the exact schemas.

### Missing required field

!!! danger "Error"
    `missing field "{field_name}"`

**Cause:** A required property is absent from the configuration JSON. All top-level properties and all properties within `adaptive`, `capture`, and `dispersion` objects are required.

**Remedy:** Add the missing field. See [Schema Reference](schema-reference.md) for the complete list of required properties.

### Invalid initial_dt

!!! danger "Error"
    `initial_dt must be positive`

**Cause:** `initial_dt` is set to zero or a negative value.

**Remedy:** Set `initial_dt` to a positive number (e.g., `0.1`).

### Invalid max_dt

!!! danger "Error"
    `max_dt must be positive`

**Cause:** `max_dt` is set to zero or a negative value.

**Remedy:** Set `max_dt` to a positive number (e.g., `10.0`).

### Invalid direction

!!! danger "Error"
    `direction must be 1.0 (forward) or -1.0 (backward)`

**Cause:** The `direction` field is not exactly `1.0` or `-1.0`.

**Remedy:** Use `1.0` for forward tracking or `-1.0` for backward tracking. No other values are accepted.

### Negative dispersivity

!!! danger "Error"
    `dispersivity values must be non-negative`

**Cause:** One or more dispersivity parameters (`alpha_l`, `alpha_th`, `alpha_tv`) are negative when using Gsde or Ito dispersion.

**Remedy:** Set all dispersivity values to zero or positive numbers.

---

## Runtime Errors — Solver Step Failures

Raised during `run_simulation()`. Each error includes a machine-readable `code` and `action` for programmatic handling.

### Particle exited domain

!!! danger "Error"
    `particle exited domain at stage {stage}`

**Code:** `DOMAIN_EXIT`  
**Retryable:** No  
**Action:** `terminate_particle`

**Cause:** During an RK stage evaluation, the particle position fell outside the model grid domain. This is a terminal condition — the particle trajectory ends here.

**Remedy:** Check that particle starting positions are within the grid. For particles near boundaries, this is expected behavior. The `final_status` of the `TrajectoryResult` will indicate domain exit.

### Dry cell encountered

!!! danger "Error"
    `dry cell {cell_id} encountered at stage {stage}`

**Code:** `DRY_CELL`  
**Retryable:** No  
**Action:** `terminate_particle`

**Cause:** The particle entered a cell where the saturated thickness is zero (water table at or below cell bottom). No velocity can be computed.

**Remedy:** Verify the head and water table arrays. Dry cells are expected in unsaturated regions. The particle trajectory terminates at the dry cell boundary.

### Non-finite velocity

!!! danger "Error"
    `non-finite velocity at ({x}, {y}, {z})`

**Code:** `NON_FINITE_VELOCITY`  
**Retryable:** Yes  
**Action:** `retry_with_dt_scale(0.5)`

**Cause:** Velocity evaluation returned NaN or infinity. Typically occurs near singularities (e.g., well screens, very thin saturated zones, near-zero porosity).

**Remedy:** The solver will automatically retry with a smaller step size. If the problem persists, check cell properties (porosity, saturated thickness) near the reported coordinates.

### Step size too small

!!! danger "Error"
    `step size {dt} below minimum {min_dt}`

**Code:** `STEP_TOO_SMALL`  
**Retryable:** No  
**Action:** `use_euler_fallback`

**Cause:** The adaptive step-size controller shrunk the time step below `adaptive.min_dt` (default: $10^{-30}$) without achieving the error tolerance. This typically indicates a stiff region in the velocity field.

**Remedy:** The embedded solvers fall back to Euler when $\Delta t < \texttt{euler\_dt}$. If this error persists, increase `adaptive.tolerance` or check for abrupt velocity changes in the model.

### Maximum iterations exceeded

!!! danger "Error"
    `exceeded {max_iters} adaptive iterations`

**Code:** `MAX_ITERATIONS`  
**Retryable:** Yes  
**Action:** `retry_with_dt_scale(0.25)`

**Cause:** The adaptive solver rejected the step `adaptive.max_rejects` times without converging. The error tolerance cannot be met at any step size.

**Remedy:** Increase `adaptive.max_rejects` or relax `adaptive.tolerance`. Check the velocity field for discontinuities near the particle location.

---

## Grid/Data Errors

Raised during `build_grid()`, `hydrate_cell_properties()`, `hydrate_cell_flows()`, `hydrate_waterloo_inputs()`, or `fit_waterloo()`.

### Mismatched array lengths

!!! danger "Error"
    `Array '{name}' has length {actual}, expected {expected}`

**Cause:** A numpy array passed to a hydration function has a different length than the number of cells in the grid.

**Remedy:** Ensure all arrays have exactly `n_cells` elements, matching the grid constructed by `build_grid()`.

### Mismatched cell counts

!!! danger "Error"
    `{DataType} has {n1} cells but grid has {n2}`

**Cause:** The `CellProperties`, `CellFlows`, or `WaterlooInputs` object was hydrated with a different number of cells than the grid.

**Remedy:** Rebuild the data objects using arrays that match the grid cell count.

### Non-contiguous array

!!! danger "Error"
    `Array '{name}' must be a contiguous 1D numpy.{dtype} array`

**Cause:** A numpy array is not C-contiguous in memory (e.g., a Fortran-order array, a slice, or a transposed view).

**Remedy:** Call `numpy.ascontiguousarray(arr)` before passing the array to mod-PATH3DU.

### Invalid face_offset array

!!! danger "Error"
    `Array 'face_offset' must start with 0`

!!! danger "Error"
    `Array 'face_offset' must be non-decreasing`

!!! danger "Error"
    `Array 'face_offset' last value is {actual}, but expected {expected} to match number of face rows`

**Cause:** The `face_offset` array (CSR-style row pointer for face connectivity) has invalid structure.

**Remedy:** `face_offset` must be a non-decreasing uint64 array of length `n_cells + 1`, starting at 0 and ending at the total number of faces.

### GridHandle already consumed

!!! danger "Error"
    `GridHandle is not loaded (already consumed or empty)`

**Cause:** The `GridHandle` was already passed to `fit_waterloo()`, which takes ownership of the grid data. The handle cannot be reused.

**Remedy:** Call `build_grid()` again to create a new handle if you need to fit a second velocity field.

### WaterlooFieldHandle not loaded

!!! danger "Error"
    `WaterlooFieldHandle is not loaded`

**Cause:** Attempting to run a simulation with a field handle that is empty or was not properly initialized.

**Remedy:** Ensure `fit_waterloo()` completed successfully and the returned handle is passed directly to `run_simulation()`.

### Invalid cell footprint

!!! danger "Error"
    `Invalid footprint for cell {idx}: {details}`

**Cause:** A cell polygon passed to `build_grid()` cannot form a valid polygon (e.g., fewer than 3 vertices, self-intersecting boundary).

**Remedy:** Verify the vertex list for the indicated cell. Each cell needs at least 3 non-collinear vertices forming a simple polygon.

### Vertices/centers length mismatch

!!! danger "Error"
    `'vertices' has {n1} cells but 'centers' has {n2}`

**Cause:** The `vertices` and `centers` lists passed to `build_grid()` have different lengths.

**Remedy:** Both lists must have exactly the same number of entries — one per cell.

### Invalid IFACE value

!!! danger "Error"
    `IFACE value {value} is not supported. Must be one of 0, 2, 5, 6, 7.`

**Cause:** The `bc_iface` array passed to `hydrate_cell_flows()` contains an unsupported value. Only IFACE values 0, 2, 5, 6, and 7 are valid.

**Remedy:** Check the IFACE assignments for your boundary condition packages. See [IFACE & Boundary Capture](../concepts/iface-boundary-capture.md) for the supported values and their meanings.

### Boundary array length mismatch

!!! danger "Error"
    `bc_cell_ids has length {n1} but bc_flow has length {n2}; all bc_* arrays must have equal length`

**Cause:** The parallel boundary condition arrays (`bc_cell_ids`, `bc_iface`, `bc_flow`, `bc_type_id`) have inconsistent lengths. All must have the same number of entries.

**Remedy:** Ensure every BC entry has corresponding values in all four arrays. Each index represents one boundary condition record.

### bc_type_id out of range

!!! danger "Error"
    `bc_type_id value {id} is out of range for bc_type_names of length {n}`

**Cause:** A value in the `bc_type_id` array exceeds the number of strings in `bc_type_names`. The `bc_type_id` values are 0-based indices into the `bc_type_names` list.

**Remedy:** Ensure all values in `bc_type_id` are in the range `[0, len(bc_type_names) - 1]`. Add any missing type names to `bc_type_names`.
