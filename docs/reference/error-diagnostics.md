# Error Diagnostics

Catalog of known error conditions in mod-PATH3DU. Errors in the inputs surface as Python `ValueError` exceptions with descriptive messages; an argument of the wrong type or array dtype raises `TypeError`.

!!! info "Initial Version"
    This catalog is initially hand-authored from codebase knowledge. Each error lists the exact or templated message text, cause, and remedy.

---

## Configuration Errors

Raised during `SimulationConfig.from_json()` or `SimulationConfig.validate()`. Both also issue a Python `UserWarning` for settings that are valid but probably not intended, such as an `adaptive.euler_dt` well above `adaptive.min_dt`.

### Invalid JSON syntax

!!! danger "Error"
    `expected value at line {line} column {col}`

**Cause:** The JSON string passed to `SimulationConfig.from_json()` is not valid JSON (missing commas, unclosed braces, trailing commas, etc.).

**Remedy:** Validate the JSON with a linter or `json.loads()` before passing to `from_json()`.

### Minimum step above maximum step

!!! danger "Error"
    `adaptive.min_dt must be a number no larger than max_dt`

**Cause:** `adaptive.min_dt` is larger than `max_dt`, or one of them is not a number, so no step size is admissible.

**Remedy:** Set `adaptive.min_dt` well below `max_dt`.

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

### Unknown field

!!! danger "Error"
    ``unknown field `{key}`, expected one of `{field}`, `{field}`, ...``

**Cause:** The configuration JSON contains a key that is not a property of the configuration, usually a misspelling such as `capture_raduis`. Before 0.1.4 such a key was ignored without notice, so a misspelled optional key silently left its setting at the default (for `capture_radius`, capture on entry to the well cell).

**Remedy:** Correct or remove the key. The message lists the keys accepted at that level. Comments cannot be kept as extra keys (for example `"_comment"`); keep them outside the JSON.

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

**Remedy:** Use `1.0` for forward tracking or `-1.0` for backward tracking. No other values are accepted; `1` and `-1` written as integers are the same values and are accepted.

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

**Remedy:** Set `adaptive.euler_dt` equal to `adaptive.min_dt`. The adaptive solvers take one Euler step when $\Delta t \le \texttt{euler\_dt}$, so this error can occur only while `euler_dt` is below `min_dt`. If it persists, increase `adaptive.tolerance` or check for abrupt velocity changes in the model. A particle that has reached the edge of the domain does not raise this error; it ends as `ExitedDomain`.

### Maximum iterations exceeded

!!! danger "Error"
    `exceeded {max_iters} adaptive iterations`

**Code:** `MAX_ITERATIONS`  
**Retryable:** Yes  
**Action:** `retry_with_dt_scale(0.25)`

**Cause:** The adaptive solver rejected the step `adaptive.max_rejects` times without converging. The error tolerance cannot be met at any step size. Rejections caused by a stage point leaving the domain do not count toward the limit.

**Remedy:** Increase `adaptive.max_rejects` or relax `adaptive.tolerance`. Check the velocity field for discontinuities near the particle location.

---

## Grid/Data Errors

Raised during `build_grid()`, `hydrate_cell_properties()`, `hydrate_cell_flows()`, `hydrate_waterloo_inputs()`, `hydrate_sspa_inputs()`, `fit_waterloo()`, `fit_sspa()`, or `run_simulation()`. When `fit_waterloo()` or `fit_sspa()` rejects its inputs, the `GridHandle` stays loaded and can be passed again once the inputs are corrected.

### Wrong array type or dtype

!!! danger "Error"
    `TypeError: argument '{name}': expected a 1-D NumPy array of dtype float64, got a 1-D array of dtype int64; convert it with numpy.asarray(x, dtype="float64")`

!!! danger "Error"
    `TypeError: argument '{name}': expected a 1-D NumPy array of an integer dtype, got a 1-D array of dtype float64`

**Cause:** An array argument is not a NumPy array, or has the wrong dtype or number of dimensions. Float arrays must be `float64` and masks `bool`. The integer arrays (`face_offset`, `face_neighbor`, `bc_cell_ids`, `bc_iface`, `bc_type_id`) accept any integer dtype. Before 0.1.4 every case raised the less helpful message `'ndarray' object cannot be converted to 'PyArray<T, D>'`.

**Remedy:** Convert the array as the message says, for example `numpy.asarray(x, dtype="float64")` or `mask.astype(bool)`. `centers_xy` must be 2-D with shape `(n_cells, 2)`.

### Integer value out of range

!!! danger "Error"
    `Array '{name}' has value {value} at index {index}, outside the range of {type}`

**Cause:** A value in one of the integer arrays does not fit the type it is stored in: a negative `face_offset` (`uint64`), or a `bc_iface` or `bc_type_id` beyond the range of `int32`. Values are checked one by one and never cast silently.

**Remedy:** Correct the value at the reported index.

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

**Remedy:** Call `numpy.ascontiguousarray(arr)` before passing the array to mod-PATH3DU. The integer arrays (`face_offset`, `face_neighbor` and the `bc_*` ids and codes) need not be contiguous.

### Invalid face_offset array

!!! danger "Error"
    `Array 'face_offset' must start with 0`

!!! danger "Error"
    `Array 'face_offset' must be non-decreasing`

!!! danger "Error"
    `Array 'face_offset' last value is {actual}, but expected {expected} to match number of face rows`

**Cause:** The `face_offset` array (CSR-style row pointer for face connectivity) has invalid structure.

**Remedy:** `face_offset` must be a non-decreasing integer array (any integer dtype) of length `n_cells + 1`, starting at 0 and ending at the total number of faces.

### GridHandle already consumed

!!! danger "Error"
    `GridHandle is not loaded`

**Cause:** The `GridHandle` was already passed to a successful `fit_waterloo()` or `fit_sspa()` call, which takes ownership of the grid data, or it was created empty with `GridHandle()`. A fitting call that raises `ValueError` leaves the handle loaded.

**Remedy:** Call `build_grid()` again to create a new handle if you need to fit a second velocity field.

### VelocityFieldHandle not loaded

!!! danger "Error"
    `VelocityFieldHandle is not loaded`

**Cause:** Attempting to run a simulation, or call `velocity_at()`, with a field handle that is empty (for example one created with `VelocityFieldHandle()`, also known as `WaterlooFieldHandle()`).

**Remedy:** Ensure `fit_waterloo()` or `fit_sspa()` completed successfully and the returned handle is passed directly to `run_simulation()`.

### Vertical connectivity out of range

!!! danger "Error"
    `top neighbor length mismatch: expected {n_cells}, got {n}` (likewise `bot neighbor`)

!!! danger "Error"
    `{top|bottom} neighbor of cell {cell} is {neighbor}, but the grid has {n_cells} cells`

!!! danger "Error"
    `nodes_per_layer is {n}, which does not divide the {n_cells} cells of the grid (use 0 for a single layer)`

**Cause:** The `top_neighbor`, `bot_neighbor` or `nodes_per_layer` arguments of `fit_waterloo()` do not describe the grid: a list of the wrong length, a neighbor id that is not a cell of the grid, or a layer size that does not divide the number of cells. Before 0.1.4 an out-of-range neighbor ended the Python process when a particle crossed that face, and a wrong `nodes_per_layer` could leave a particle in one cell until `max_steps`.

**Remedy:** Give one entry per cell, with `None` where there is no cell above or below, and set `nodes_per_layer` to the number of cells per layer (0 for a single layer).

### Particle cell outside the field

!!! danger "Error"
    `particle {id} has cell_id {cell_id}, but the velocity field has {n_cells} cells`

**Cause:** A `ParticleStart.cell_id` passed to `run_simulation()` is not a cell of the fitted field.

**Remedy:** Use the zero-based index of the cell that contains the particle's starting point.

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
    `Invalid IFACE value {value} for cell {cell} bc_type_id {type_id}`

**Cause:** The `bc_iface` array passed to `hydrate_cell_flows()` contains an unsupported value. Only IFACE values 0, 2, 5, 6, and 7 are valid.

**Remedy:** Check the IFACE assignments for your boundary condition packages. See [IFACE & Boundary Capture](../concepts/iface-boundary-capture.md) for the supported values and their meanings.

### Boundary array length mismatch

!!! danger "Error"
    `Array 'bc_iface' has length {n1}, expected {n2}` (likewise `bc_flow`, `bc_type_id`)

!!! danger "Error"
    `bc_cell_ids, bc_iface, bc_flow, and bc_type_id must all be provided or all be None`

**Cause:** The parallel boundary condition arrays (`bc_cell_ids`, `bc_iface`, `bc_flow`, `bc_type_id`) have inconsistent lengths (each is compared with `bc_cell_ids`), or only some of the four were given.

**Remedy:** Ensure every BC entry has corresponding values in all four arrays. Each index represents one boundary condition record. To pass `is_domain_boundary` or `has_water_table` without boundary conditions, omit all four `bc_*` arrays.

### bc_cell_ids out of range

!!! danger "Error"
    `bc_cell_ids[{i}] = {id} is out of range [0, {n_cells})`

**Cause:** A boundary condition entry refers to a cell that does not exist. Cell ids are 0-based.

**Remedy:** Check the conversion from MODFLOW's 1-based node numbers to 0-based cell ids.

### bc_type_id without a name

This is not an error. A `bc_type_id` value that has no entry in `bc_type_names` (0-based index) is reported in `termination_reason` as `BC_TYPE_{id}`, for example `Internal sink/source: BC_TYPE_3`. Add the missing names to `bc_type_names` to get readable reasons.

---

## Internal Errors

### PanicException

!!! danger "Error"
    `pyo3_runtime.PanicException: {message}`

**Cause:** An internal check in mod-PATH3DU's Rust code failed. This indicates a bug or an input that is not yet validated. Since 0.1.4 it raises this exception; before, it ended the Python process without a message. `PanicException` derives from `BaseException`, not `Exception`, so `except Exception:` does not catch it.

**Remedy:** Please report it with the message and, if possible, the inputs that produced it.
