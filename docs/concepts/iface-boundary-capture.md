# IFACE & Boundary Capture

How mod-PATH3DU uses MODFLOW IFACE values to route boundary condition flows
and terminate particles at the correct cell face.

---

## What is IFACE?

In MODFLOW, a boundary condition (BC) entry can specify which **face** of a
cell receives the BC flow via the `IFACE` parameter. This is critical for
particle tracking because it determines:

1. **Which velocity-field term** the BC flow contributes to
   (`q_well`, `q_other`, `q_top`, or `q_bot`).
2. **Where the particle is captured** when it reaches a cell with an active BC.

Without IFACE, the tracker has no way of knowing whether a constant-head
boundary acts on the side, top, or bottom of a cell, and cannot produce
physically correct pathlines near boundaries.

---

## Supported IFACE Values

| IFACE | Face | Flow Bucket | Capture Class | Description |
|-------|------|-------------|---------------|-------------|
| 0 | Cell centre | `q_well` | `InternalWell` | Well or point sink/source at cell centre |
| 2 | Side face | `q_other` | `Internal` | Distributed BC across the cell's lateral faces |
| 5 | Bottom face | `q_bot` | `BottomFace` | BC at the cell bottom (e.g., leakage) |
| 6 | Top face | `q_top` | `TopFace` | BC at the cell top (e.g., recharge, ET) |
| 7 | Internal | `q_top` | `Internal` | Internal BC, no well — flow routed to top |

!!! warning "Only these five IFACE values are supported"
    Values 1, 3, and 4 are not supported and will raise an error.

---

## Typical IFACE Settings by BC Package

| MODFLOW Package | Typical IFACE | Rationale |
|----------------|--------------|-----------|
| **WEL** | 0 | Well at cell centre |
| **CHD** | 2 | Constant-head boundary on cell sides |
| **GHB** | 2 | General-head boundary on cell sides |
| **RCH** | 6 | Recharge applied at cell top |
| **EVT** | 6 | Evapotranspiration at cell top |
| **DRN** | 6 | Drain at cell top |
| **RIV** | 6 or 5 | River — top (shallow) or bottom (deep) |

These are defaults; your model may differ depending on how the stress
packages were configured. Always check the MODFLOW input files or
documentation for your specific model.

---

## How IFACE Affects the Velocity Field

The Waterloo velocity method reconstructs the cell's internal velocity from
boundary fluxes. Each IFACE value routes the BC flow to a specific term in
the velocity equation:

- **IFACE 0** → `q_well`: subtracted via singularity subtraction during
  polynomial fitting, then added back during evaluation. This produces the
  characteristic radial flow pattern around a well.
- **IFACE 2** → `q_other`: added to the distributed source/sink term.
  Contributes to the uniform volumetric flux within the cell.
- **IFACE 5** → `q_bot`: added to the bottom-face vertical flux.
  Affects the vertical velocity component.
- **IFACE 6** → `q_top`: added to the top-face vertical flux.
  Affects the vertical velocity component.
- **IFACE 7** → `q_top` (with sign negation): treated the same as IFACE 6
  for velocity purposes, but classified differently for capture.

### Sign Conventions

All `bc_flow` values use **raw MODFLOW sign** (negative = extraction,
positive = injection). The Rust hydration layer applies internal negation
for IFACE 0, 6, and 7:

| IFACE | Internal Negation? | Reason |
|-------|-------------------|--------|
| 0 | Yes | Waterloo singularity subtraction convention |
| 2 | No | Direct addition to `q_other` |
| 5 | No | Direct addition to `q_bot` |
| 6 | Yes | Top-face sign convention |
| 7 | Yes | Same as IFACE 6 for flow routing |

See [Units & Conventions — IFACE Sign Conventions](../reference/units-and-conventions.md#iface-sign-conventions) for the complete reference.

---

## How IFACE Affects Particle Capture

When a particle enters a cell with boundary entries, the tracker checks
whether the particle should be terminated. The checks follow a strict
**priority chain** (highest to lowest):

### 1. Domain Boundary

If `is_domain_boundary[cell] = True` **and** the cell has no IFACE 0 entry,
the particle is terminated with status `CapturedAtModelEdge`.

### 2. InternalWell (IFACE 0)

If the cell has an IFACE 0 entry, the particle is checked against
`capture_radius`:

- **`capture_radius` omitted / null**: capture immediately on cell entry
  (strong-sink).
- **`capture_radius` = R**: capture only when the particle is within
  distance $R$ of the cell centre (weak-sink).

Status: `CapturedByWell`.

### 3. Internal (IFACE 2, 7)

If the cell has an IFACE 2 or 7 entry and the flow direction indicates a
sink, capture triggers immediately on cell entry.

Status: `CapturedByBoundary`.

### 4. TopFace (IFACE 6) / BottomFace (IFACE 5)

If the cell has an IFACE 6 or 5 entry, the particle is checked against a
face proximity criterion:

- **Top face (IFACE 6)**: $z > 1 - \texttt{face\_epsilon}$ **and**
  flow sign indicates active BC **and** vertical velocity is upward.
- **Bottom face (IFACE 5)**: $z < \texttt{face\_epsilon}$ **and**
  flow sign indicates active BC.

Status: `CapturedByBoundary`.

The `face_epsilon` parameter (default: $10^{-6}$) is configured in the
`capture` block of `SimulationConfig`.

### Mutual Exclusivity

Each priority level is checked in order. Once a match is found, no
lower-priority checks are performed. This means:

- A cell with both IFACE 0 and IFACE 2 entries → well capture wins.
- A cell with IFACE 6 → captured only when near the top face, not on entry.

---

## Water_Table Special Case

The `has_water_table` flag marks cells in unconfined or convertible layers.
When set, an additional capture check occurs for **forward-tracking**
simulations: if a particle reaches the top of the cell (water table), it is
terminated. This mimics the physical reality that particles cannot travel
above the water table in an unconfined aquifer.

This check is separate from the IFACE priority chain and applies even without
boundary entries.

---

## Default IFACE

If a BC package is not in your IFACE configuration, its entries should
default to **IFACE 7** (internal BC with no well). This ensures that:

1. The BC flow contributes to the velocity field (via `q_top`).
2. Particles entering the cell are captured immediately.

---

## Migration from `has_well`

Prior to IFACE-based capture, the only mechanism for terminating particles at
internal sinks was the `has_well` flag. Legacy scripts often used
`has_well=True` for non-well BCs (e.g., CHD cells) as a workaround to force
capture.

### Recommended Migration Steps

1. **Identify all BC cells** in your MODFLOW model with their IFACE values.
2. **Build `bc_*` arrays** from your MODFLOW CBC output using the
   [`route_iface_bc_flows()`](../reference/iface-flow-routing.md) helper.
3. **Pass `bc_*` arrays** to `hydrate_cell_flows()`.
4. **Set `has_well`** only for actual wells (IFACE 0), or leave it as all-False
   and let the `bc_*` arrays handle everything.
5. **Remove** any `has_well=True` entries that were workarounds for CHD/RCH/etc.

!!! warning "Deprecation"
    Setting `has_well=True` for non-well BCs is deprecated. When `bc_*` arrays
    are present, `has_well` is ignored for cells that have boundary entries.

---

## See Also

- [IFACE Flow Routing](../reference/iface-flow-routing.md) — Technical spec
  for flow routing and the `route_iface_bc_flows()` helper
- [Units & Conventions](../reference/units-and-conventions.md#iface-based-boundary-flow-routing)
  — Sign conventions and array ordering
- [Building Configs — Capture Behaviour](../guides/building-configs.md#capture-behaviour)
  — Configuration reference for `capture_radius` and `face_epsilon`
- [Boundary Capture Example](../examples/boundary-capture.md) — End-to-end
  example with CHD boundaries
