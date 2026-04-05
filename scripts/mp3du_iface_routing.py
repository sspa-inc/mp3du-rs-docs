"""
IFACE-based boundary condition flow routing for mp3du-rs.

This module provides a helper function that routes MODFLOW boundary condition
flows to the correct mp3du flow-term arrays based on their IFACE assignment.

The routing follows the C++ mod-PATH3DU implementation in
``cls_flowmodel.cpp`` and is specified in
``docs/reference/iface-flow-routing.md``.

Usage
-----
::

    from mp3du_iface_routing import route_iface_bc_flows

    routes = route_iface_bc_flows(
        n_cells=n_cells,
        bc_cell_ids=bc_cell_ids,   # 0-based cell indices
        bc_iface=bc_iface,         # IFACE values (0, 2, 5, 6, 7)
        bc_flow=bc_flow,           # raw MODFLOW sign
    )

    # Add routed BC flows to existing arrays:
    q_well_arr += routes["q_well"]
    q_other_arr += routes["q_other"]
    q_top_arr += routes["q_top"]
    q_bot_arr += routes["q_bot"]

    # has_well is auto-set for cells with IFACE 0 entries:
    has_well_arr |= routes["has_well"]

Sign Conventions
----------------
All input ``bc_flow`` values use the **raw MODFLOW sign** (negative =
extraction / out of aquifer, positive = injection / into aquifer).

The routing function applies the appropriate sign transformation per IFACE:

=====  ============  =============  ====================================
IFACE  Target Array  Sign Applied   C++ Reference
=====  ============  =============  ====================================
  0    q_well        Negate         ``set_qwel(-1.*(*pdata[m]))``
  2    q_other       Raw            ``set_qother(*pdata[m])``
  5    q_bot         Raw            ``set_qbot(*pdata[m])``
  6    q_top         Negate         ``set_qtop(-1.*(*pdata[m]))``
  7    q_top         Negate         ``set_qtop(-1.*(*pdata[m]))``
=====  ============  =============  ====================================

Each BC flow is routed to **exactly one** bucket (no double counting).

q_vert Note
-----------
The ``q_vert`` array passed to ``hydrate_waterloo_inputs()`` must contain
**cell-to-cell vertical flow only** — it must NOT include BC contributions
from IFACE 5/6/7.  The BC contributions to ``q_top``/``q_bot`` are used
only by the evaluation context (Pollock vertical velocity interpolation),
not by the fitting correction term.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# Valid IFACE values accepted by mp3du-rs
VALID_IFACE_VALUES = frozenset({0, 2, 5, 6, 7})


def route_iface_bc_flows(
    n_cells: int,
    bc_cell_ids: NDArray[np.int64],
    bc_iface: NDArray[np.int32],
    bc_flow: NDArray[np.float64],
) -> dict[str, NDArray]:
    """Route IFACE-tagged BC flows to Waterloo velocity-method flow arrays.

    Parameters
    ----------
    n_cells : int
        Total number of cells in the model.
    bc_cell_ids : ndarray of int64, shape (n_bc,)
        0-based cell indices for each BC record.
    bc_iface : ndarray of int32, shape (n_bc,)
        IFACE value for each BC record.  Must be one of {0, 2, 5, 6, 7}.
    bc_flow : ndarray of float64, shape (n_bc,)
        BC flow rate for each record, in **raw MODFLOW sign** convention
        (negative = extraction, positive = injection).

    Returns
    -------
    dict with keys:
        ``"q_well"``   : ndarray float64, shape (n_cells,)
            IFACE 0 flows, **negated** (matching C++ ``set_qwel(-1*val)``).
            Add to q_well arrays for both ``hydrate_cell_flows()`` and
            ``hydrate_waterloo_inputs()``.
        ``"q_other"``  : ndarray float64, shape (n_cells,)
            IFACE 2 flows, **raw MODFLOW sign**.
            Add to q_other for ``hydrate_waterloo_inputs()``.
        ``"q_top"``    : ndarray float64, shape (n_cells,)
            IFACE 6 + 7 flows, **negated** (matching C++ ``set_qtop(-1*val)``).
            Add to q_top for ``hydrate_cell_flows()``.
        ``"q_bot"``    : ndarray float64, shape (n_cells,)
            IFACE 5 flows, **raw MODFLOW sign**.
            Add to q_bot for ``hydrate_cell_flows()``.
        ``"has_well"`` : ndarray bool, shape (n_cells,)
            True for cells with any IFACE 0 entry.

    Raises
    ------
    ValueError
        If arrays have mismatched lengths, cell IDs are out of range,
        or IFACE values are not in {0, 2, 5, 6, 7}.

    Examples
    --------
    >>> import numpy as np
    >>> routes = route_iface_bc_flows(
    ...     n_cells=10,
    ...     bc_cell_ids=np.array([0, 3, 5], dtype=np.int64),
    ...     bc_iface=np.array([2, 0, 6], dtype=np.int32),
    ...     bc_flow=np.array([-1.5, -10.0, 0.01], dtype=np.float64),
    ... )
    >>> routes["q_other"][0]   # IFACE 2: raw sign
    -1.5
    >>> routes["q_well"][3]    # IFACE 0: negated
    10.0
    >>> routes["q_top"][5]     # IFACE 6: negated
    -0.01
    >>> routes["has_well"][3]
    True
    """
    bc_cell_ids = np.asarray(bc_cell_ids, dtype=np.int64)
    bc_iface = np.asarray(bc_iface, dtype=np.int32)
    bc_flow = np.asarray(bc_flow, dtype=np.float64)

    n_bc = len(bc_cell_ids)
    if len(bc_iface) != n_bc or len(bc_flow) != n_bc:
        raise ValueError(
            f"Array length mismatch: bc_cell_ids={n_bc}, "
            f"bc_iface={len(bc_iface)}, bc_flow={len(bc_flow)}"
        )

    # Validate IFACE values
    unique_iface = set(int(v) for v in np.unique(bc_iface))
    invalid = unique_iface - VALID_IFACE_VALUES
    if invalid:
        raise ValueError(
            f"Invalid IFACE values: {sorted(invalid)}. "
            f"Must be one of {sorted(VALID_IFACE_VALUES)}."
        )

    # Validate cell IDs
    if n_bc > 0:
        if bc_cell_ids.min() < 0 or bc_cell_ids.max() >= n_cells:
            bad = bc_cell_ids[(bc_cell_ids < 0) | (bc_cell_ids >= n_cells)]
            raise ValueError(
                f"bc_cell_ids out of range [0, {n_cells}): {bad[:5].tolist()}"
            )

    q_well = np.zeros(n_cells, dtype=np.float64)
    q_other = np.zeros(n_cells, dtype=np.float64)
    q_top = np.zeros(n_cells, dtype=np.float64)
    q_bot = np.zeros(n_cells, dtype=np.float64)
    has_well = np.zeros(n_cells, dtype=np.bool_)

    if n_bc == 0:
        return {
            "q_well": q_well,
            "q_other": q_other,
            "q_top": q_top,
            "q_bot": q_bot,
            "has_well": has_well,
        }

    # IFACE 0 → q_well (negate)
    mask_0 = bc_iface == 0
    if mask_0.any():
        np.add.at(q_well, bc_cell_ids[mask_0], -bc_flow[mask_0])
        has_well[np.unique(bc_cell_ids[mask_0])] = True

    # IFACE 2 → q_other (raw sign)
    mask_2 = bc_iface == 2
    if mask_2.any():
        np.add.at(q_other, bc_cell_ids[mask_2], bc_flow[mask_2])

    # IFACE 5 → q_bot (raw sign)
    mask_5 = bc_iface == 5
    if mask_5.any():
        np.add.at(q_bot, bc_cell_ids[mask_5], bc_flow[mask_5])

    # IFACE 6 → q_top (negate)
    mask_6 = bc_iface == 6
    if mask_6.any():
        np.add.at(q_top, bc_cell_ids[mask_6], -bc_flow[mask_6])

    # IFACE 7 → q_top (negate)
    mask_7 = bc_iface == 7
    if mask_7.any():
        np.add.at(q_top, bc_cell_ids[mask_7], -bc_flow[mask_7])

    return {
        "q_well": q_well,
        "q_other": q_other,
        "q_top": q_top,
        "q_bot": q_bot,
        "has_well": has_well,
    }
