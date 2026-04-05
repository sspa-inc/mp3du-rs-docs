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

### Flow rates

| Quantity | Convention | Description |
|----------|------------|-------------|
| Face flow (MODFLOW CBC) | positive = **out of** the cell | Raw MODFLOW cell-by-cell budget output |
| Face flow (Waterloo inputs) | positive = **into** the cell | **Negate** MODFLOW face flows before passing to `hydrate_waterloo_inputs()` |
| Face flow (cell_flows) | positive = **out of** the cell | Pass raw MODFLOW face flows to `hydrate_cell_flows()` — no negation |
| `q_top` positive | Flow entering through the top face (from above) | |
| `q_bot` positive | Flow entering through the bottom face (from below) | |
| `q_well` (MODFLOW) | **negative** = pumping (extraction), positive = injection | Raw MODFLOW sign |
| `q_well` (Waterloo inputs) | Same as MODFLOW — **do NOT negate** | Pass raw MODFLOW sign to `hydrate_waterloo_inputs()` |
| `q_well` (cell_flows) | Same as MODFLOW — **do NOT negate** | Pass raw MODFLOW sign to `hydrate_cell_flows()` |

### Sign Conversion Cheat Sheet

When loading MODFLOW binary output into mp3du, apply these transformations:

```python
# Face flows: NEGATE for Waterloo inputs, raw for cell_flows
waterloo_face_flow = -modflow_face_flow   # flip sign for Waterloo
cell_flows_face_flow = modflow_face_flow  # keep raw for cell_flows

# Well Q: NEVER negate — pass raw MODFLOW sign to both
waterloo_q_well = modflow_q_well          # raw sign (negative = extraction)
cell_flows_q_well = modflow_q_well        # raw sign (negative = extraction)
```

!!! warning "Why q_well is NOT negated"
    The Waterloo method uses singularity subtraction: during **fitting**, the analytic well contribution is subtracted from boundary flux data using $Q_\text{well}$. During **evaluation**, the same analytic term is added back. Both operations must use the **same** $Q_\text{well}$ value. The C++ implementation passes the raw MODFLOW sign (negative for extraction) to both fitting and evaluation. If you negate $Q_\text{well}$ for fitting but not evaluation (or vice versa), the subtraction/addition will not cancel and the velocity field will be **asymmetrically distorted** around the well.

!!! warning "Why face flow IS negated"
    MODFLOW defines positive face flow as **out of** the cell. The Waterloo fitting algorithm defines positive face flow as **into** the cell (inward normal convention). The C++ implementation (`cls_flowmodel.cpp`) negates face flows when loading them: `cell->cxn_flows[cxn] = -1.0 * (*pdata[m])`. You must do the same.

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

Particle starting positions (`ParticleStart`) use the same coordinate system as the grid:

| Field | Description |
|-------|-------------|
| `x`, `y`, `z` | Position in model coordinates |
| `cell_id` | 0-based index of the containing cell |
| `initial_dt` | Initial time step magnitude (model time units) |

The `cell_id` must correspond to a valid cell index in the grid. The particle's `(x, y)` position should be within the polygon footprint of the specified cell. The `z` coordinate should be between `bot[cell_id]` and `top[cell_id]`.

---

## Trajectory Output

`TrajectoryResult.to_records()` returns a list of dictionaries with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `step` | int | Step number (0-based) |
| `time` | float | Accumulated simulation time |
| `x`, `y`, `z` | float | Particle position in model coordinates |
| `vx`, `vy`, `vz` | float | Velocity components at this position |
| `cell_id` | int | Cell containing the particle at this step |
| `dt` | float | Time step size used for this step |

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
