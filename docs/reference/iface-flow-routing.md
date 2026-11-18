# IFACE Flow Routing — Specification

This document defines the exact mapping between MODFLOW IFACE values and
the flow-term "buckets" used by the mp3du Waterloo velocity method.

---

## Background

MODFLOW boundary condition packages (CHD, WEL, RCH, DRN, GHB, etc.) can
assign an **IFACE** value to each stress entry.  IFACE tells the particle
tracker which cell face (or cell interior) the boundary flow acts on.
This controls both **capture termination logic** (Phase A) and **velocity
field construction** (Phase B).

The C++ reference implementation routes IFACE-tagged flows in
`cls_flowmodel.cpp` during CBC budget parsing.  This document specifies
the equivalent mapping for mp3du-rs, implemented in Python.

---

## IFACE Values Supported

| IFACE | Meaning | C++ Code Reference |
|-------|---------|-------------------|
| 0 | Internal well (flow applied at cell centre) | `set_qwel(-1.*(*pdata[m]))` |
| 2 | Side face / distributed (flow distributed to cell perimeter) | `set_qother(*pdata[m])` |
| 5 | Bottom face (flow applied at cell bottom) | `set_qbot(*pdata[m])` |
| 6 | Top face (flow applied at cell top) | `set_qtop(-1.*(*pdata[m]))` |
| 7 | Internal, no well singularity (flow applied at cell top, negated) | `set_qtop(-1.*(*pdata[m]))` |

IFACE values 1, 3, 4 (per-connection side-face assignment) are **not
supported** in either C++ mod-PATH3DU or mp3du-rs.

---

## Flow Bucket Mapping

### Waterloo Fitting Inputs (`CellFitInput` / `hydrate_waterloo_inputs`)

The Waterloo fitting uses three flow terms: `q_well`, `q_other`, and
`q_vert`.  IFACE 0 and 2 enter `q_well` and `q_other`; IFACE 5, 6 and 7
enter `q_vert`, as in mod-PATH3DU, where `qtop` and `qbot` are part of
`qvert = (qtop - qbot) + (qtopface - qbotface) - qsto` (`cls_cell.cpp` L556):

| IFACE | Target Field | Sign Transformation | Rationale |
|-------|-------------|---------------------|-----------|
| 0 | `q_well` | **Negate** MODFLOW value | C++: `set_qwel(-1.*val)`.  The Waterloo method subtracts the analytic well singularity during fitting and adds it back during evaluation.  Both use this negated value. |
| 2 | `q_other` | **Raw** MODFLOW sign | C++: `set_qother(val)`.  Distributed to no-flow faces during fitting. |
| 5 | `q_vert` | see [`q_vert`](#q_vert-consistency-audit-results) | C++: `set_qbot(val)`; `qbot` is part of `qvert`.  Also in `q_bot` for vertical velocity. |
| 6 | `q_vert` | see [`q_vert`](#q_vert-consistency-audit-results) | C++: `set_qtop(-1.*val)`; `qtop` is part of `qvert`.  Also in `q_top` for vertical velocity. |
| 7 | `q_vert` | see [`q_vert`](#q_vert-consistency-audit-results) | Same as IFACE 6. |

### Evaluation Context (`CellEvalContext` / `fit_waterloo`)

The evaluation context uses `q_well`, `q_bot_total`, and `q_top_total`
for vertical velocity interpolation (Pollock's method):

| IFACE | Target Field | Sign Transformation | Rationale |
|-------|-------------|---------------------|-----------|
| 0 | `q_well` | **Negate** MODFLOW value | Same negated value as fitting.  Used for the well singularity correction in `eval_waterloo_velocity()`. |
| 2 | *(not in eval context)* | — | Absorbed into horizontal velocity during fitting. |
| 5 | `q_bot_total` | **Raw** MODFLOW sign | C++: `set_qbot(val)`.  Added to cell-to-cell bottom flow for Pollock vz interpolation. |
| 6 | `q_top_total` | **Negate** MODFLOW value | C++: `set_qtop(-1.*val)`.  Added to cell-to-cell top flow for Pollock vz interpolation. |
| 7 | `q_top_total` | **Negate** MODFLOW value | C++: `set_qtop(-1.*val)`.  Same treatment as IFACE 6. |

### Summary Table

| IFACE | `CellFitInput.q_well` | `CellFitInput.q_other` | `CellFlows.q_top` | `CellFlows.q_bot` | Sign |
|-------|----------------------|----------------------|-------------------|-------------------|------|
| 0 | ✓ | | | | Negate |
| 2 | | ✓ | | | Raw |
| 5 | | | | ✓ | Raw |
| 6 | | | ✓ | | Negate |
| 7 | | | ✓ | | Negate |

!!! warning "Each IFACE routes to exactly ONE bucket"
    A BC flow must never be double-counted.  IFACE 2 flows go to `q_other`
    only — they do NOT additionally contribute to `q_top` or `q_bot`.
    IFACE 7 flows go to `q_top` only — they do NOT go to `q_other`.

---

## `q_vert` Consistency — Audit Results

`q_vert` is the net vertical flow used as a correction term in the Waterloo
horizontal velocity fitting.  As in mod-PATH3DU, it is minus the net inflow
through the cell's top and bottom faces: cell-to-cell flow **and** boundary
flow routed to those faces (IFACE 5, 6 and 7).  Storage is passed separately
in `q_storage`.

The simplest way to get it right is the cell water balance.  For a cell whose
MODFLOW budget closes,

```
q_vert = sum(face_flow) + q_well + q_other + q_storage
```

with `face_flow` positive into the cell and `q_well`, `q_other` and `q_storage`
in raw MODFLOW sign.  This holds whatever sign convention is used for `q_top`
and `q_bot`.

!!! warning "Changed in 0.1.2"
    Earlier versions of this page said that boundary flows routed to `q_top` /
    `q_bot` must not be included in `q_vert`.  That disagreed with mod-PATH3DU:
    leaving recharge out of `q_vert` leaves it out of the horizontal fit, just as
    leaving storage out did before 0.1.2.

### Audit Trace

The following code paths were verified:

1. **Fitting** (`fitting.rs` L145): `q_vert` is used in the boundary normal
   flux correction term `qn_vert = -q_vert/area * Re(local) * radius * cos(theta)`.
   This value comes from `CellFitInput.q_vert`, which is populated by
   `hydrate_waterloo_inputs()` from its `q_vert` parameter — a separate
   Python array that must contain the vertical flow through the top and
   bottom faces (cell-to-cell and boundary), without storage.

2. **Evaluation** (`eval.rs` L103-104): `q_bot_total` and `q_top_total` are
   used for Pollock vertical velocity interpolation:
   ```
   v_bot = q_bot_total / porosity / area
   v_top = q_top_total / porosity / area
   vz = ((1 - z) * v_bot + z * v_top) / sat_thickness
   ```
   These come from `CellEvalContext`, built in `functions.rs` L143-144 from
   `CellFlows.q_bot[i]` and `CellFlows.q_top[i]` — the arrays passed to
   `hydrate_cell_flows()`.

3. **Eval context `q_vert`** (`functions.rs`): `CellEvalContext.q_vert`
   is set from `CellFlows.q_vert[i] - CellFlows.q_storage[i]`.  It is used in
   the evaluation for the horizontal velocity vertical-flow correction (same
   formula as fitting).

4. **Storage** (`functions.rs`, since 0.1.2): `fit_waterloo()` subtracts
   `CellFlows.q_storage` from the `q_vert` of both the fit inputs and the
   evaluation contexts, as the C++ does
   (`qvert = (qtop-qbot) + (qtopface-qbotface) - qsto`, `cls_cell.cpp` L556).
   `q_storage` is MODFLOW's storage flow, positive = released from storage
   into the cell (MF6: `STO-SS + STO-SY`).  Neither `q_vert` array may
   contain storage.  Before 0.1.2, `q_storage` was accepted but not used.

### Consistency Guarantee

The two hydration functions receive **independent** `q_vert` parameters:

| Function | `q_vert` Source | Contains |
|----------|----------------|----------|
| `hydrate_waterloo_inputs(q_vert=...)` | Python `q_vert` array | Cell-to-cell + BC (IFACE 5/6/7), without storage |
| `hydrate_cell_flows(q_vert=...)` | the same `q_vert` array | Cell-to-cell + BC (IFACE 5/6/7), without storage |
| `hydrate_cell_flows(q_top=...)` | Python `q_top` array | Cell-to-cell + BC (IFACE 6/7) |
| `hydrate_cell_flows(q_bot=...)` | Python `q_bot` array | Cell-to-cell + BC (IFACE 5) |
| `hydrate_cell_flows(q_storage=...)` | Python `q_storage` array | Storage flow, raw MODFLOW sign; subtracted from both `q_vert` arrays by `fit_waterloo()` |

The `CellFlows.q_top` and `CellFlows.q_bot` arrays carry the **total**
vertical flow (cell-to-cell + BC contributions) for use by the evaluation
context (vertical velocity).  `q_vert` carries the same flows, combined into
one net term, for the horizontal fit.  Pass the same `q_vert` to both
functions.

This is consistent as long as Python assembles the arrays as:

```python
# Vertical term from the cell water balance: face_flow positive into the cell;
# q_well, q_other and q_storage in raw MODFLOW sign. It contains cell-to-cell
# and boundary flow through the top and bottom faces, but not storage.
cell_in = np.add.reduceat(face_flow, face_offset[:-1].astype(np.intp))
q_vert = cell_in + q_well + q_other + q_storage

# TOTAL flows through the top and bottom faces (for vertical velocity)
q_top_total = q_top_c2c + bc_q_top  # IFACE 6 + 7, negated
q_bot_total = q_bot_c2c + bc_q_bot  # IFACE 5, raw

# Storage, raw MODFLOW sign (MF6: STO-SS + STO-SY); zeros for steady state
q_storage = sto_ss + sto_sy

# hydrate_cell_flows gets TOTAL (cell-to-cell + BC) and the storage flow
cell_flows = mp3du.hydrate_cell_flows(..., q_top=q_top_total, q_bot=q_bot_total,
                                      q_vert=q_vert, q_storage=q_storage, ...)

# hydrate_waterloo_inputs gets the same q_vert
waterloo_inputs = mp3du.hydrate_waterloo_inputs(..., q_vert=q_vert, ...)
```

---

## Python Routing Helper

The `route_iface_bc_flows()` helper function in `scripts/mp3du_iface_routing.py`
implements this mapping.  See [IFACE Routing Utility](../scripts/mp3du_iface_routing.py)
for the reference implementation and unit tests.
