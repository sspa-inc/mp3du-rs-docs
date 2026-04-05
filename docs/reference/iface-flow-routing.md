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
`q_vert`.  Only IFACE 0 and IFACE 2 affect fitting inputs:

| IFACE | Target Field | Sign Transformation | Rationale |
|-------|-------------|---------------------|-----------|
| 0 | `q_well` | **Negate** MODFLOW value | C++: `set_qwel(-1.*val)`.  The Waterloo method subtracts the analytic well singularity during fitting and adds it back during evaluation.  Both use this negated value. |
| 2 | `q_other` | **Raw** MODFLOW sign | C++: `set_qother(val)`.  Distributed to no-flow faces during fitting. |
| 5 | *(not a fitting input)* | — | Bottom-face flow only affects vertical velocity interpolation. |
| 6 | *(not a fitting input)* | — | Top-face flow only affects vertical velocity interpolation. |
| 7 | *(not a fitting input)* | — | Same as IFACE 6 for flow routing; affects `q_top_total` in evaluation only. |

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
horizontal velocity fitting.  It represents **cell-to-cell** vertical flow
only:

```
q_vert = q_top_cell2cell - q_bot_cell2cell
```

**BC flows routed to `q_top` / `q_bot` must NOT be included in `q_vert`.**

### Audit Trace

The following code paths were verified:

1. **Fitting** (`fitting.rs` L145): `q_vert` is used in the boundary normal
   flux correction term `qn_vert = -q_vert/area * Re(local) * radius * cos(theta)`.
   This value comes from `CellFitInput.q_vert`, which is populated by
   `hydrate_waterloo_inputs()` from its `q_vert` parameter — a separate
   Python array that must contain cell-to-cell vertical flow only.

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

3. **Eval context `q_vert`** (`functions.rs` L143): `CellEvalContext.q_vert`
   is set from `CellFlows.q_vert[i]`.  This is the same value as passed by
   Python to `hydrate_cell_flows()`.  It is used in the evaluation for the
   horizontal velocity vertical-flow correction (same formula as fitting).

### Consistency Guarantee

The two hydration functions receive **independent** `q_vert` parameters:

| Function | `q_vert` Source | Contains |
|----------|----------------|----------|
| `hydrate_waterloo_inputs(q_vert=...)` | Python `q_vert` array | Cell-to-cell only |
| `hydrate_cell_flows(q_vert=...)` | Python `q_vert` array | Cell-to-cell only |
| `hydrate_cell_flows(q_top=...)` | Python `q_top` array | Cell-to-cell + BC (IFACE 6/7) |
| `hydrate_cell_flows(q_bot=...)` | Python `q_bot` array | Cell-to-cell + BC (IFACE 5) |

The `CellFlows.q_top` and `CellFlows.q_bot` arrays carry the **total**
vertical flow (cell-to-cell + BC contributions) for use by the evaluation
context.  The `q_vert` passed to `hydrate_waterloo_inputs()` must remain
as cell-to-cell vertical flow only.

This is consistent as long as Python assembles the arrays as:

```python
# Cell-to-cell vertical flows from FLOWJA
q_top_c2c = ...  # from FLOW LOWER FACE or FLOWJA for upper neighbor
q_bot_c2c = ...  # from FLOW LOWER FACE or FLOWJA for lower neighbor
q_vert = q_top_c2c - q_bot_c2c  # for hydrate_waterloo_inputs ONLY

# Add BC contributions to the TOTAL arrays (for hydrate_cell_flows)
q_top_total = q_top_c2c + bc_q_top  # IFACE 6 + 7, negated
q_bot_total = q_bot_c2c + bc_q_bot  # IFACE 5, raw

# hydrate_cell_flows gets TOTAL (cell-to-cell + BC)
cell_flows = mp3du.hydrate_cell_flows(..., q_top=q_top_total, q_bot=q_bot_total, ...)

# hydrate_waterloo_inputs gets cell-to-cell ONLY for q_vert
waterloo_inputs = mp3du.hydrate_waterloo_inputs(..., q_vert=q_vert, ...)
```

---

## Python Routing Helper

The `route_iface_bc_flows()` helper function in `scripts/mp3du_iface_routing.py`
implements this mapping.  See [IFACE Routing Utility](../../scripts/mp3du_iface_routing.py)
for the reference implementation and unit tests.
