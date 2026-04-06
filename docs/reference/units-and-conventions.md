# Units and Conventions

Coordinate system, unit expectations, and sign conventions for mod-PATH3DU.

---

## Coordinate System

mod-PATH3DU uses a **right-handed Cartesian coordinate system** consistent with MODFLOW-USG:

| Axis | Direction | Description |
|------|-----------|-------------|
| X | Horizontal (east) | Model easting coordinate |
| Y | Horizontal (north) | Model northing coordinate |
| Z | Vertical (up) | Elevation above datum |

Cell geometry is defined by 2D polygonal footprints in the XY plane plus top/bottom elevations in Z. The grid supports unstructured (arbitrary polygon) cells as used in MODFLOW-USG.

---

## Units

!!! warning "Unit Consistency"
    mod-PATH3DU does **not** perform unit conversions. All input data must use consistent units matching the MODFLOW model.

| Quantity | Expected Unit | Notes |
|----------|--------------|-------|
| Length | Model length units (m or ft) | Coordinates, elevations, dispersivities |
| Time | Model time units (d or s) | Step sizes, max_time, velocities |
| Velocity | Length / Time | Derived from flow and geometry |
| Dispersivity | Length | Same length unit as model — `alpha_l`, `alpha_th`, `alpha_tv` |
| Flow rate | Length³ / Time | Face flows, well rates, top/bottom fluxes |
| Hydraulic head | Length | Same length unit as model |
| Porosity | Dimensionless | 0 < n ≤ 1 |
| Retardation | Dimensionless | ≥ 1.0 |
| Hydraulic conductivity | Length / Time | `hhk` (horizontal), `vhk` (vertical) |

---

## Direction Convention

The `direction` field in `SimulationConfig` controls tracking direction:

| Value | Meaning |
|-------|---------|
| `1.0` | Forward tracking (in the direction of flow) |
| `-1.0` | Backward tracking (reverse flow direction) |

!!! info "Schema Constraint"
    The `direction` field accepts **only** `1.0` or `-1.0` (enum constraint in JSON Schema). No other values are valid.

Forward tracking computes where particles **will go** from their starting positions. Backward tracking computes where particles **came from** — useful for delineating capture zones.

---

## Sign Conventions

!!! danger "Critical — Read This Before Writing Data-Loading Code"
    The sign conventions for flow rates differ between MODFLOW output and the mp3du Waterloo fitting inputs. Getting these wrong produces **silently incorrect** velocity fields — particles will follow plausible-looking but physically wrong trajectories. The table below is the authoritative reference.

!!! danger "MODFLOW Version Matters — Different Versions Use Different Raw Signs"
    Different MODFLOW versions store cell-by-cell (CBC) face flows with
    **fundamentally different** sign conventions.  You **must** know which
    MODFLOW variant produced your flow data before passing it to mp3du:

    | MODFLOW Version | CBC Record Type | Raw Sign Convention |
    |-----------------|-----------------|---------------------|
    | **MODFLOW-2005 / NWT** (structured) | `FLOW RIGHT FACE`, `FLOW FRONT FACE`, `FLOW LOWER FACE` | Positive = flow in direction of **increasing row/column/layer index** (directional, not in/out) |
    | **MODFLOW-USG** (unstructured) | `FLOW JA FACE` / `FLOW-JA-FACE` | Positive = flow **INTO** the cell from the neighbour |
    | **MODFLOW 6** (unstructured) | `FLOW-JA-FACE` (or API `FLOWJA`) | Positive = flow **INTO** the cell from the neighbour |

    The mp3du API defines its own consistent convention that is
    **independent of the MODFLOW version**.  Your data-loading code must
    transform whatever raw MODFLOW output you have into these mp3du
    conventions — see the conversion table below.

### mp3du API Convention (Target)

These are the conventions mp3du expects **after** you have done any
necessary sign transformation:

| Function | `face_flow` Convention | `q_well` Convention |
|----------|----------------------|---------------------|
| `hydrate_cell_flows()` | positive = **INTO** cell | raw MODFLOW sign (negative = extraction) |
| `hydrate_waterloo_inputs()` | positive = **INTO** cell | raw MODFLOW sign (negative = extraction) |

Both hydration functions accept the **same** `face_flow` array — convert
once to positive = INTO, then pass the result to both.

### Flow rates

| Quantity | Convention | Description |
|----------|------------|-------------|
| Face flow (`hydrate_cell_flows`) | positive = **into** the cell | mp3du convention; transform your MODFLOW output to match |
| Face flow (`hydrate_waterloo_inputs`) | positive = **into** the cell | same array as `hydrate_cell_flows` — no separate transformation |
| `q_top` positive | Flow entering through the top face (from above) | |
| `q_bot` positive | Flow entering through the bottom face (from below) | |
| `q_well` (everywhere) | **negative** = pumping (extraction), positive = injection | Raw MODFLOW sign — **never negate** |

### Sign Conversion by MODFLOW Version

The transformation from raw MODFLOW output to mp3du convention depends on
which MODFLOW version produced the data.

#### MODFLOW-USG / MODFLOW 6 (`FLOW-JA-FACE` or API `FLOWJA`)

Raw sign: **positive = INTO cell**. mp3du also uses positive = INTO, so
**pass directly** to both functions — no negation needed.

```python
# MODFLOW-USG/MF6 FLOW-JA-FACE: positive = INTO cell
face_flow = flowja_face_flow   # pass directly: already positive = INTO
# Pass face_flow to BOTH hydrate_cell_flows() and hydrate_waterloo_inputs()
```

#### MODFLOW-2005 / NWT (Structured: `FLOW RIGHT FACE` etc.)

Structured MODFLOW stores **directional** inter-cell flows — **not**
per-cell in/out flows.  The raw convention is positive in the direction
of increasing row or column number:

- `FLOW RIGHT FACE` at (row, col): positive = flow from cell (row, col) → cell (row, col+1) (in the +column direction).
- `FLOW FRONT FACE` at (row, col): positive = flow from cell (row, col) → cell (row+1, col) (in the +row direction).
- `FLOW LOWER FACE` at (row, col): positive = flow downward from cell (row, col, lay) → cell (row, col, lay+1).

A single stored value describes flow **between two cells**: it is
simultaneously an outflow for one cell and an inflow for the other.
You must convert these directional flows to **per-cell per-face** flows
during CSR assembly.  The assembly step looks at each face from the
perspective of the current cell and flips the sign when the face's
stored direction points *into* the cell:

```python
# FLOW RIGHT FACE at (row, col) = positive in +column direction
# When assembling faces for cell (r, c):
if neighbor is to the right:   flow = +frf[r, c]      # same direction as stored → OUT
if neighbor is to the left:    flow = -frf[r, c - 1]   # reverse direction → OUT

# FLOW FRONT FACE at (row, col) = positive in +row direction
if neighbor is below (front):  flow = +fff[r, c]       # same direction → OUT
if neighbor is above (back):   flow = -fff[r - 1, c]   # reverse direction → OUT
```

After this directional-to-per-face conversion, the resulting values follow
**positive = OUT of cell** convention — **negate once** before passing to
both functions:

```python
face_flow = -assembled_face_flow  # negate: positive = INTO cell
# Pass face_flow to BOTH hydrate_cell_flows() and hydrate_waterloo_inputs()
```

!!! tip "mp3du adopts the MODFLOW-USG / MF6 convention"
    The mp3du Python API uses the same sign convention as MODFLOW-USG and
    MODFLOW 6 `FLOW-JA-FACE`: **positive = flow entering the cell through
    that face**.  MODFLOW-2005 / NWT users must negate `face_flow` once
    after directional-to-per-face assembly to match this convention.

### Quick-Reference Cheat Sheet

```python
# ── MODFLOW-USG / MF6 (FLOW-JA-FACE / FLOWJA) ──
face_flow = flowja                  # pass directly: already positive = INTO

# ── MODFLOW-2005 / NWT (after directional → per-face assembly) ──
face_flow = -assembled              # negate once: positive = INTO

# Pass the SAME face_flow to BOTH hydrate_cell_flows() and
# hydrate_waterloo_inputs(). No per-function negation needed.

# ── Well Q: NEVER negate — pass raw MODFLOW sign to BOTH functions ──
q_well = modflow_q_well             # raw sign (negative = extraction)
```

!!! warning "Why q_well is NOT negated"
    The Waterloo method uses singularity subtraction: during **fitting**, the analytic well contribution is subtracted from boundary flux data using $Q_\text{well}$. During **evaluation**, the same analytic term is added back. Both operations must use the **same** $Q_\text{well}$ value. The C++ implementation passes the raw MODFLOW sign (negative for extraction) to both fitting and evaluation. If you negate $Q_\text{well}$ for fitting but not evaluation (or vice versa), the subtraction/addition will not cancel and the velocity field will be **asymmetrically distorted** around the well.

!!! info "Direct `q_well` arrays vs. IFACE-routed `bc_flow`"
    The raw-sign rule above applies to direct per-cell `q_well` arrays passed to
    `hydrate_cell_flows()` or `hydrate_waterloo_inputs()`. If you instead start
    from IFACE-tagged boundary records, keep `bc_flow` in raw MODFLOW sign and
    let the IFACE routing step apply the documented per-IFACE transformation
    before accumulating into `q_well`, `q_top`, or `q_bot`.

!!! info "Why both functions accept the same face_flow array"
    The `face_flow` array uses a single unified sign convention
    (**positive = INTO cell**) for both `hydrate_cell_flows()` and
    `hydrate_waterloo_inputs()`.  Convert your MODFLOW output once and
    pass the same array to both.  No per-function negation is needed.

### Velocity

Velocity components (`vx`, `vy`, `vz`) represent the **average linear velocity** (seepage velocity) — the Darcy flux divided by porosity. The direction follows the Cartesian axes: positive `vx` is in the +X direction.

### Elevations and Saturated Thickness

- `top` = top elevation of the cell
- `bot` = bottom elevation of the cell
- `water_table` = water table elevation (**layer-type dependent** — see table below)
- Saturated thickness = `water_table - bot` (clamped to ≥ 0)

!!! danger "CRITICAL — Layer-Type-Dependent Water Table"
    The `water_table` array passed to `hydrate_cell_flows()` directly controls
    the saturated thickness used to convert the Waterloo stream function into
    velocity: `vx = Re(dΩ) / sat_thick / porosity`. Getting this wrong produces
    **silently incorrect velocities** — typically 2×–17× too fast for confined
    layers. There is no runtime warning; the particles simply follow wrong
    trajectories that look plausible.

    The correct value depends on the **MODFLOW layer type** (LAYTYP / LAYCON
    from the LPF, UPW, or NPF package):

    | LAYTYP | Layer Type | `water_table` | `sat_thick` |
    |--------|------------|---------------|-------------|
    | 0 | **Confined** | `top` | `top - bot` (full layer thickness) |
    | 1 | **Unconfined** | `head` | `head - bot` |
    | > 0 | **Convertible** | `min(head, top)` | `min(head, top) - bot` |

    The C++ implementation applies this automatically in `cls_cell.cpp` when
    reading heads (`cell->wt = cell->top` for confined; `cell->wt = cell->head`
    for unconfined/convertible with head < top). Python scripts using the Rust
    API must replicate this logic explicitly — see Example 4a.

    **Diagnostic check**: If your Rust velocities are a constant multiple of
    the C++ reference, compare `water_table` values. For confined models,
    `water_table` should equal `top` everywhere, NOT `head`.

```python
# Correct water_table assignment (MODFLOW LPF/UPW)
laytyp = m.lpf.laytyp.array  # per-layer array
for ci in range(n_cells):
    layer = cell_layer[ci]  # 0-based layer index
    lt = int(laytyp[layer])
    if lt == 0:                                     # confined
        wt_arr[ci] = cell_top[ci]
    elif lt == 1:                                   # unconfined
        wt_arr[ci] = head_arr[ci]
    else:                                           # convertible
        wt_arr[ci] = min(head_arr[ci], cell_top[ci])
```

### IFACE-Based Boundary Flow Routing

When a MODFLOW boundary condition package assigns an IFACE value to a stress
entry, the BC flow must be routed to the correct mp3du flow-term array.  See
[IFACE Flow Routing](iface-flow-routing.md) for the complete specification,
sign conventions, and the ``route_iface_bc_flows()`` Python helper.

#### IFACE Sign Conventions

All `bc_flow` values passed to `hydrate_cell_flows()` use **raw MODFLOW sign**
(negative = extraction/out of cell, positive = injection/into cell). The Rust
hydration layer applies any internal negation as needed:

| IFACE | Target Array | Internal Negation? | Notes |
|-------|-------------|-------------------|-------|
| 0 | `q_well` | Yes (negate) | Well at cell centre |
| 2 | `q_other` | No (raw) | Distributed side-face BC |
| 5 | `q_bot` | No (raw) | Bottom-face BC |
| 6 | `q_top` | Yes (negate) | Top-face BC (e.g., recharge) |
| 7 | `q_top` | Yes (negate) | Internal BC, no well |

#### Aggregation Rule

Multiple BC entries for the same cell are summed per flow bucket, matching the
C++ `bcs[] +=` semantics. The `route_iface_bc_flows()` helper uses
`np.add.at()` for this purpose.

#### Backward Compatibility

When `bc_*` arrays are provided to `hydrate_cell_flows()`, boundary-info-based
capture replaces the legacy `has_well`-only mechanism for cells that have
boundary entries. For cells with no boundary entries, `has_well` still controls
well capture.

!!! warning "Deprecation Notice"
    Setting `has_well=True` as a workaround for non-well BCs (e.g., CHD cells)
    is deprecated. Use the `bc_*` arrays with proper IFACE values instead.
    The `has_well` field remains for backward compatibility with scripts that
    do not use IFACE-based boundary data.

---

## Array Ordering

All per-cell arrays are **0-indexed** and ordered by cell index (matching the order cells are passed to `build_grid()`):

| Array | Length | Indexing |
|-------|--------|---------|
| `top`, `bot`, `porosity`, etc. | `n_cells` | `arr[i]` = value for cell `i` |
| `head`, `water_table`, `q_*` | `n_cells` | `arr[i]` = value for cell `i` |
| `has_well` | `n_cells` | `arr[i]` = `True` if cell `i` has a well |

### Cell Vertex Winding Order (CW REQUIRED)

!!! danger "Silent geometry error — no runtime validation"
    All cell polygons passed to `build_grid()` **must** be wound
    **Clockwise (CW)** when viewed from above (looking down the −Z
    axis).  The code does **not** validate winding order.  Counter-clockwise
    (CCW) vertices silently flip face normals, producing a 180° reversed
    velocity field.

    **Diagnostic**: Compute the signed area with the shoelace formula.
    Negative area = CW (correct).  Positive area = CCW (wrong).

    **If your source data is CCW**: reverse the vertex list and negate all
    `face_flow` values.

### Face-to-Vertex Index Mapping

For a cell with *N* vertices `[v0, v1, ..., v_{N-1}]` in CW order:

- **Face 0** = edge `v0 → v1`
- **Face 1** = edge `v1 → v2`
- ...
- **Face N-1** = edge `v_{N-1} → v0`

All face-level arrays (`face_flow`, `face_vx1/vy1/vx2/vy2`, `face_length`,
`face_neighbor`, `noflow_mask`) follow this indexing.  For example,
`face_vx1[i], face_vy1[i]` are the coordinates of vertex `i` (the start of
face `i`), and `face_vx2[i], face_vy2[i]` are the coordinates of vertex
`(i+1) % N` (the end of face `i`).

### Boundary condition arrays (parallel, variable-length)

The optional `bc_*` arrays passed to `hydrate_cell_flows()` are parallel arrays
indexed by boundary condition entry (not by cell). All must have the same
length (`n_bc_entries`):

| Array | Dtype | Description |
|-------|-------|-------------|
| `bc_cell_ids` | `int64` | 0-based cell index for each BC entry |
| `bc_iface` | `int32` | IFACE value (0, 2, 5, 6, or 7) |
| `bc_flow` | `float64` | Flow rate (raw MODFLOW sign) |
| `bc_type_id` | `int32` | Index into `bc_type_names` |
| `bc_type_names` | `List[str]` | Human-readable BC type names (e.g., `["CONSTANT HEAD", "WELLS"]`) |
| `is_domain_boundary` | `bool` (n_cells) | `True` if cell is at the model domain edge |
| `has_water_table` | `bool` (n_cells) | `True` if cell is unconfined/convertible |

!!! info "`is_domain_boundary` and `has_water_table`"
    These two arrays are per-cell (`n_cells`), not per-BC-entry.

### Face connectivity (CSR layout)

Face-level data uses a Compressed Sparse Row (CSR) layout:

| Array | Length | Description |
|-------|--------|-------------|
| `face_offset` | `n_cells + 1` | `face_offset[i]` to `face_offset[i+1]` spans face entries for cell `i` |
| `face_flow` | total faces | Flow rate across each face |
| `face_neighbor` | total faces | Neighbor cell ID for each face (`-1` for boundary/no-flow) |

```python
# Example: get face flows for cell i
start = face_offset[i]
end = face_offset[i + 1]
cell_face_flows = face_flow[start:end]
cell_face_neighbors = face_neighbor[start:end]
```

The `face_offset` array must:

- Start with `0`
- Be non-decreasing
- End with the total number of face entries

---

## Particle Coordinates

Particle starting positions (`ParticleStart`) use XY model coordinates but **local normalized Z**:

| Field | Description |
|-------|-------------|
| `x`, `y` | Position in model (global) coordinates |
| `z` | **Local vertical coordinate in [0, 1]**: 0.0 = cell bottom, 1.0 = cell top, 0.5 = layer midpoint |
| `cell_id` | 0-based index of the containing cell |
| `initial_dt` | Initial time step magnitude (model time units) |

!!! danger "CRITICAL — z is LOCAL, not a physical elevation"
    `z` is a **normalized local coordinate** in the range [0, 1], NOT a physical
    elevation in model units.  If you pass a physical elevation (e.g. `z=5.0`
    when `top=10.0, bot=0.0`), the particle will immediately exit the cell
    because 5.0 > 1.0.

    To convert a physical elevation to local z:
    ```python
    z_local = (z_physical - bot[cell_id]) / (top[cell_id] - bot[cell_id])
    ```

    This follows the MODPATH convention (Dave Pollock) where all vertical
    tracking is done in local cell coordinates.

The `cell_id` must correspond to a valid cell index in the grid. The particle's `(x, y)` position should be within the polygon footprint of the specified cell.

---

## Trajectory Output

`TrajectoryResult.to_records()` returns a list of dictionaries with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `step` | int | Step number (0-based) |
| `time` | float | Accumulated simulation time |
| `x`, `y` | float | Particle position in model (global) coordinates |
| `z` | float | **Local vertical coordinate in [0, 1]** (NOT physical elevation) |
| `vx`, `vy`, `vz` | float | Velocity components at this position |
| `cell_id` | int | Cell containing the particle at this step |
| `dt` | float | Time step size used for this step |

!!! info "Converting output z to physical elevation"
    ```python
    z_global = bot[rec['cell_id']] + rec['z'] * (top[rec['cell_id']] - bot[rec['cell_id']])
    ```

The `final_status` field on `TrajectoryResult` is a string describing why tracking ended:

| Status | Meaning |
|--------|---------|
| `CapturedByWell` | Particle reached a well (IFACE 0) within capture radius |
| `CapturedByBoundary` | Particle terminated by an IFACE 2/5/6/7 boundary condition |
| `CapturedAtModelEdge` | Particle reached a domain-edge cell (`is_domain_boundary = True`) |
| `Exited` | Particle left the grid domain |
| `MaxTime` | `capture.max_time` was reached |
| `MaxSteps` | `capture.max_steps` was reached |
| `Stagnated` | Velocity below threshold for N consecutive steps |
| `Error` | A solver error occurred |

The `termination_reason` field provides additional detail for capture events.
For boundary captures it includes the BC type name, e.g.,
`"Internal sink/source: CONSTANT HEAD"`. For non-capture terminations it
mirrors the `final_status` string.
