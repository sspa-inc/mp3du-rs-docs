"""Type stubs for the mp3du Rust particle tracker."""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import numpy.typing as npt


def version() -> str:
    """Return the version string of the installed mp3du library."""
    ...


class WaterlooConfig:
    """Configuration for the Waterloo polynomial velocity-field fitting method.

    The Waterloo method fits a polynomial velocity field to the discrete
    face-by-face flows from an unstructured MODFLOW grid by minimising a
    least-squares system at a set of interior control points.

    Args:
        order_of_approx: Order of the polynomial approximation (total number
            of basis functions). Higher values capture more spatial detail but
            increase memory and solve time. Default is ``35``.
        n_control_points: Number of control points distributed inside the
            fitting domain. Must be ≥ ``order_of_approx``. Default is ``122``.
    """

    def __init__(self, order_of_approx: int = 35, n_control_points: int = 122) -> None: ...

    @property
    def order_of_approx(self) -> int:
        """Order of the polynomial approximation (number of basis functions)."""
        ...

    @property
    def n_control_points(self) -> int:
        """Number of control points used in the polynomial least-squares fit."""
        ...


class SimulationConfig:
    """Top-level simulation configuration object.

    Typically constructed from a JSON string (or file) via
    `SimulationConfig.from_json()`.  The JSON must conform to the
    [Schema Reference](../../reference/schema-reference.md).
    """

    @staticmethod
    def from_json(json_str: str) -> "SimulationConfig":
        """Deserialize a ``SimulationConfig`` from a JSON string.

        Args:
            json_str: A JSON string that conforms to the mp3du configuration schema.

        Returns:
            A validated ``SimulationConfig`` instance.

        Raises:
            ValueError: If the JSON is malformed, a value is missing or
                invalid, or the JSON contains a key that the configuration
                does not have (for example, a misspelled key).

        A ``UserWarning`` is issued for settings that are valid but
        probably not intended, such as ``adaptive.euler_dt`` well above
        ``adaptive.min_dt``.
        """
        ...

    def to_json(self) -> str:
        """Serialize this configuration to a JSON string.

        Returns:
            A compact JSON representation of the configuration.
        """
        ...

    def validate(self) -> None:
        """Validate the configuration against the schema.

        Raises:
            ValueError: If any field value is out of range or inconsistent.

        Like ``from_json()``, issues a ``UserWarning`` for settings that are
        valid but probably not intended.
        """
        ...


class ParticleStart:
    """Defines a single particle's starting position and initial tracking step.

    Attributes:
        id: User-supplied integer identifier for this particle.
        x: Starting X coordinate (model units, global).
        y: Starting Y coordinate (model units, global).
        z: Starting Z coordinate — **local normalized value in [0, 1]**.
            ``0.0`` = cell bottom, ``1.0`` = cell top, ``0.5`` = layer
            midpoint.  This is **NOT** a physical elevation.  To convert:
            ``z_local = (z_physical - bot) / (top - bot)``.
            Passing a physical elevation (e.g. ``z=5.0`` when ``top=10,
            bot=0``) causes immediate ``ExitedDomain`` because ``5.0 > 1.0``.
        cell_id: Zero-based index of the MODFLOW cell that contains the
            particle's starting position.
        initial_dt: Initial time-step size for the adaptive tracker (model
            time units).  Set to a small positive value; the solver adjusts
            automatically afterwards.
    """

    id: int
    x: float
    y: float
    z: float
    cell_id: int
    initial_dt: float

    def __init__(
        self,
        id: int,
        x: float,
        y: float,
        z: float,
        cell_id: int,
        initial_dt: float,
    ) -> None: ...


class TrajectoryResult:
    """Contains the complete tracking trajectory for a single particle.

    Attributes:
        particle_id: The ``id`` supplied in the corresponding
            `ParticleStart`.
        final_status: The terminal state: ``"CapturedByWell"``,
            ``"CapturedByBoundary"``, ``"CapturedAtModelEdge"``,
            ``"ExitedDomain"``, ``"TimeLimitReached"``, ``"Stagnated"`` or
            ``"SolverFailed"``.
        termination_reason: Human-readable description of why tracking
            stopped, for example ``"Internal sink/source: CONSTANT HEAD"``,
            ``"Model Boundary"`` or ``"Time limit reached"``. It is empty
            for ``ExitedDomain`` and ``SolverFailed``.
    """

    particle_id: int
    final_status: str
    termination_reason: str

    def to_records(self) -> List[Dict[str, Any]]:
        """Convert the trajectory to a list of per-step record dicts.

        Each record contains the keys ``step``, ``time``, ``x``, ``y``,
        ``z``, ``vx``, ``vy``, ``vz``, ``cell_id`` and ``dt``.  The list
        can be passed directly to
        ``pandas.DataFrame(result.to_records())``.

        Returns:
            A list of dicts, one per recorded trajectory step.
        """
        ...

    def __len__(self) -> int:
        """Return the number of recorded trajectory steps."""
        ...


class GridHandle:
    """Opaque handle to a compiled unstructured grid.

    Produced by `build_grid()`.  The handle is *consumed* (invalidated) by
    `fit_waterloo()` or `fit_sspa()` — it cannot be reused after fitting.
    A fitting call that raises ``ValueError`` leaves it loaded.
    """

    def __init__(self) -> None:
        """An empty, unloaded handle; build_grid() returns a loaded one."""
        ...

    def is_loaded(self) -> bool:
        """Return ``True`` if the grid data is still resident in memory.

        Returns ``False`` after the handle has been consumed by a fitting call.
        """
        ...

    def n_cells(self) -> int:
        """Return the number of cells in the grid."""
        ...


class VelocityFieldHandle:
    """Opaque handle to a fitted velocity field.

    Returned by both `fit_waterloo()` and `fit_sspa()`.  Pass this handle
    to `run_simulation()` to perform particle tracking.

    ``WaterlooFieldHandle`` is another name for this class.
    """

    def __init__(self) -> None:
        """An empty, unloaded handle."""
        ...

    def is_loaded(self) -> bool:
        """Return ``True`` if the fitted field data is resident in memory."""
        ...

    def method_name(self) -> str:
        """Return the name of the fitting method used (e.g. ``"waterloo"`` or ``"sspa"``)."""
        ...

    def n_cells(self) -> int:
        """Return the number of cells in the underlying grid."""
        ...

    def velocity_at(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """Evaluate the velocity ``(vx, vy, vz)`` at the point ``(x, y, z)``.

        Raises ``ValueError`` if the handle is not loaded or the velocity
        cannot be evaluated there (for example, the point is outside the
        model).
        """
        ...


# Alias — fit_sspa() and fit_waterloo() both return the same handle type.
WaterlooFieldHandle = VelocityFieldHandle


class SspaConfig:
    """Configuration for the SSP&A (kriging-based) velocity-field fitting method.

    Args:
        search_radius: Neighbourhood search radius used when selecting
            conditioning data for each kriging estimate (model units).
            This only needs to span a few raster cells — typically 2–3×
            the cell size of the input raster.  Best practice: read the
            cell size from each input raster (e.g. via ``rasterio``) and
            set ``search_radius = 2 * cell_size`` (or ``3 * cell_size``
            for safety).  A radius that is too large wastes time and
            over-smooths; a radius that is too small under-determines
            the kriging system and produces noisy velocities. Default is
            ``35.0`` (mod-PATH3DU's value), in model units; set it from
            the raster cell size instead.
        krig_offset: Finite-difference offset used when estimating the
            kriged head gradient near the particle. Smaller values sample
            the gradient more locally; larger values smooth it over a
            wider distance. Default is ``0.1``.
    """

    def __init__(self, search_radius: float = 35.0, krig_offset: float = 0.1) -> None: ...

    @property
    def search_radius(self) -> float:
        """Neighbourhood search radius for kriging (model units).

        Should be 2–3× the raster cell size.  Read the cell size from
        each input raster and set dynamically rather than hard-coding.
        """
        ...

    @property
    def krig_offset(self) -> float:
        """Finite-difference offset for kriged gradient estimation."""
        ...


class SspaInputs:
    """Hydrated inputs for the SSP&A fitting method.

    Produced by `hydrate_sspa_inputs()`.  Pass to `fit_sspa()`.
    """

    def n_cells(self) -> int:
        """Return the number of cells represented in these inputs."""
        ...

    def __len__(self) -> int:
        """Return the number of cells (same as ``n_cells()``)."""
        ...

    @property
    def heads(self) -> List[float]:
        """Simulated hydraulic heads per cell."""
        ...

    @property
    def hydraulic_conductivity(self) -> List[float]:
        """Horizontal hydraulic conductivity per cell."""
        ...

    @property
    def hhk(self) -> List[float]:
        """Alias for ``hydraulic_conductivity``."""
        ...

    @property
    def porosity(self) -> List[float]:
        """Effective porosity per cell."""
        ...

    @property
    def well_mask(self) -> List[bool]:
        """Boolean mask marking cells that contain a well."""
        ...

    @property
    def disp_long(self) -> Optional[List[float]]:
        """Longitudinal dispersivity per cell (L), or None if not given per cell."""
        ...

    @property
    def disp_trans_h(self) -> Optional[List[float]]:
        """Horizontal transverse dispersivity per cell (L), or None if not given per cell."""
        ...

    @property
    def disp_trans_v(self) -> Optional[List[float]]:
        """Vertical transverse dispersivity per cell (L), or None if not given per cell."""
        ...


def hydrate_sspa_inputs(
    heads: npt.NDArray[np.float64],
    porosity: npt.NDArray[np.float64],
    well_mask: npt.NDArray[np.bool_],
    hydraulic_conductivity: Optional[npt.NDArray[np.float64]] = None,
    hhk: Optional[npt.NDArray[np.float64]] = None,
    disp_long: Optional[npt.NDArray[np.float64]] = None,
    disp_trans_h: Optional[npt.NDArray[np.float64]] = None,
    disp_trans_v: Optional[npt.NDArray[np.float64]] = None,
) -> SspaInputs:
    """Hydrate SSP&A fitting inputs from NumPy arrays.

    Dispersivity is given in one of two ways, never both:

    - per cell: all three of ``disp_long``, ``disp_trans_h`` and
      ``disp_trans_v``, with ``alpha_l``, ``alpha_th`` and ``alpha_tv`` left
      out of the configuration's ``dispersion`` block. For one value
      everywhere, fill the arrays with it, for example ``numpy.full(n, 10.0)``;
    - in the configuration: ``alpha_l``, ``alpha_th`` and ``alpha_tv`` in the
      ``dispersion`` block, the same in every cell, with these three arrays
      left out.

    Giving only one or two of the arrays raises ``ValueError`` here. With
    dispersion on, `run_simulation()` raises ``ValueError`` for dispersivity
    given both ways, or neither. Without dispersion the arrays are not used,
    and `run_simulation()` issues a ``UserWarning`` saying so unless every
    value is 0.

    The SSP&A field is two-dimensional, so ``disp_trans_v`` (or ``alpha_tv``)
    must be 0 in a run with dispersion.

    Args:
        heads: Simulated hydraulic heads, shape ``(n_cells,)``.
        porosity: Effective porosity per cell, shape ``(n_cells,)``.
        well_mask: Boolean array marking cells that contain a well,
            shape ``(n_cells,)``.
        hydraulic_conductivity: Horizontal hydraulic conductivity per cell,
            shape ``(n_cells,)``.  Provide exactly one of
            ``hydraulic_conductivity`` or ``hhk``.
        hhk: Alias for ``hydraulic_conductivity`` (legacy shorthand).
            Provide exactly one of ``hydraulic_conductivity`` or ``hhk``.
        disp_long: Optional longitudinal dispersivity per cell (L),
            shape ``(n_cells,)``.
        disp_trans_h: Optional horizontal transverse dispersivity per cell (L),
            shape ``(n_cells,)``.
        disp_trans_v: Optional vertical transverse dispersivity per cell (L),
            shape ``(n_cells,)``; must be 0 for a run with dispersion.

    Returns:
        An `SspaInputs` object ready to pass to `fit_sspa()`.
    """
    ...


def fit_sspa(
    config: SspaConfig,
    grid: GridHandle,
    inputs: SspaInputs,
    drifts: List[Dict[str, Any]],
) -> VelocityFieldHandle:
    """Fit the SSP&A (kriging-based) velocity field.

    Consumes the GridHandle (it will no longer be loaded after the call).
    If the inputs are rejected with ValueError, the GridHandle is left loaded.
    """
    ...


class CellProperties:
    """Per-cell physical properties used during velocity-field fitting and tracking.

    All arrays are indexed by zero-based cell ID.  Produced by
    `hydrate_cell_properties()`.
    """

    @property
    def top(self) -> List[float]:
        """Top elevation of each cell (model units)."""
        ...

    @property
    def bot(self) -> List[float]:
        """Bottom elevation of each cell (model units)."""
        ...

    @property
    def porosity(self) -> List[float]:
        """Effective porosity of each cell (dimensionless, 0–1)."""
        ...

    @property
    def retardation(self) -> List[float]:
        """Retardation factor of each cell (dimensionless, ≥ 1). Not used yet:
        MP3DU-RS does not apply retardation."""
        ...

    @property
    def hhk(self) -> List[float]:
        """Horizontal hydraulic conductivity of each cell (L/T)."""
        ...

    @property
    def vhk(self) -> List[float]:
        """Vertical hydraulic conductivity of each cell (L/T)."""
        ...

    @property
    def disp_long(self) -> Optional[List[float]]:
        """Longitudinal dispersivity of each cell (L), or None if not given per cell."""
        ...

    @property
    def disp_trans_h(self) -> Optional[List[float]]:
        """Horizontal transverse dispersivity of each cell (L), or None if not given per cell."""
        ...

    @property
    def disp_trans_v(self) -> Optional[List[float]]:
        """Vertical transverse dispersivity of each cell (L), or None if not given per cell."""
        ...

    def n_cells(self) -> int:
        """Return the number of cells."""
        ...


class CellFlows:
    """Per-cell flow data (heads, budgets, face flows) used during particle tracking.

    All arrays are indexed by zero-based cell ID.  Produced by
    `hydrate_cell_flows()`.

    !!! note "Sign conventions"
        Pass raw MODFLOW values — **do not negate**.
        ``face_flow`` positive = into cell (MODFLOW-USG / MF6 convention).
        ``q_well`` negative = extraction, positive = injection.
    """

    @property
    def head(self) -> List[float]:
        """Simulated hydraulic head in each cell (model units)."""
        ...

    @property
    def water_table(self) -> List[float]:
        """Water-table elevation in each cell (model units)."""
        ...

    @property
    def q_top(self) -> List[float]:
        """Total flow through the cell top (L³/T), positive **upward**, i.e. out of
        the cell; recharge entering the top is negative (mod-PATH3DU's
        ``qtop + qtopface``). Used for the vertical velocity."""
        ...

    @property
    def q_bot(self) -> List[float]:
        """Total flow through the cell bottom (L³/T), positive **upward**, i.e.
        into the cell from below (mod-PATH3DU's ``qbot + qbotface``). Used for
        the vertical velocity."""
        ...

    @property
    def q_vert(self) -> List[float]:
        """Net vertical flow term without storage (L³/T): minus the net inflow
        through the cell's top and bottom faces, cell-to-cell and boundary
        flows alike (mod-PATH3DU's ``(qtop - qbot) + (qtopface - qbotface)``)."""
        ...

    @property
    def q_well(self) -> List[float]:
        """Well volumetric flux (L³/T). Negative = extraction, positive = injection."""
        ...

    @property
    def q_other(self) -> List[float]:
        """Sum of all other (non-well, non-face) boundary fluxes (L³/T)."""
        ...

    @property
    def q_storage(self) -> List[float]:
        """Storage flow (L³/T, MODFLOW's sign: positive = water released from
        storage into the cell). For MODFLOW 6 the sum of ``STO-SS`` and
        ``STO-SY``; zeros for steady state. `fit_waterloo()` subtracts it
        from ``q_vert`` (since 0.1.2)."""
        ...

    @property
    def has_well(self) -> List[bool]:
        """``True`` for each cell that contains an active well."""
        ...

    @property
    def face_offset(self) -> List[int]:
        """Start index into ``face_flow`` / ``face_neighbor`` for each cell."""
        ...

    @property
    def face_flow(self) -> List[float]:
        """Face-by-face volumetric fluxes (L³/T).  Positive = into cell."""
        ...

    @property
    def face_neighbor(self) -> List[Optional[int]]:
        """Zero-based cell index of the neighbouring cell across each face,
        or ``None`` for domain-boundary faces."""
        ...

    def n_cells(self) -> int:
        """Return the number of cells."""
        ...


class WaterlooInputs:
    """Hydrated inputs for the Waterloo polynomial velocity-field fitting method.

    Produced by `hydrate_waterloo_inputs()`.  Pass to `fit_waterloo()`.

    !!! note "Sign convention"
        ``face_flow`` here uses the same convention as ``CellFlows``
        (positive = INTO cell).  Pass the **same** ``face_flow`` array
        to both ``hydrate_cell_flows()`` and ``hydrate_waterloo_inputs()``.
    """

    def n_cells(self) -> int:
        """Return the number of cells represented in these inputs."""
        ...

    def __len__(self) -> int:
        """Return the number of cells (same as ``n_cells()``)."""
        ...


def hydrate_cell_properties(
    top: npt.NDArray[np.float64],
    bot: npt.NDArray[np.float64],
    porosity: npt.NDArray[np.float64],
    retardation: npt.NDArray[np.float64],
    hhk: npt.NDArray[np.float64],
    vhk: npt.NDArray[np.float64],
    disp_long: Optional[npt.NDArray[np.float64]] = None,
    disp_trans_h: Optional[npt.NDArray[np.float64]] = None,
    disp_trans_v: Optional[npt.NDArray[np.float64]] = None,
) -> CellProperties:
    """Hydrate per-cell physical properties from NumPy arrays.

    All arrays must have shape ``(n_cells,)`` and be in cell-ID order.

    Dispersivity is given in one of two ways, never both:

    - per cell: all three of ``disp_long``, ``disp_trans_h`` and
      ``disp_trans_v``, with ``alpha_l``, ``alpha_th`` and ``alpha_tv`` left
      out of the configuration's ``dispersion`` block. For one value
      everywhere, fill the arrays with it, for example ``numpy.full(n, 10.0)``;
    - in the configuration: ``alpha_l``, ``alpha_th`` and ``alpha_tv`` in the
      ``dispersion`` block, the same in every cell, with these three arrays
      left out.

    Giving only one or two of the arrays raises ``ValueError`` here. With
    dispersion on, `run_simulation()` raises ``ValueError`` for dispersivity
    given both ways, or neither. Without dispersion the arrays are not used,
    and `run_simulation()` issues a ``UserWarning`` saying so unless every
    value is 0.

    Args:
        top: Top elevation of each cell (model units).
        bot: Bottom elevation of each cell (model units).
        porosity: Effective porosity (dimensionless, 0–1).
        retardation: Retardation factor (dimensionless, ≥ 1). Not used yet:
            MP3DU-RS does not apply retardation.
        hhk: Horizontal hydraulic conductivity (L/T).
        vhk: Vertical hydraulic conductivity (L/T).
        disp_long: Optional longitudinal dispersivity per cell (L).
        disp_trans_h: Optional horizontal transverse dispersivity per cell (L).
        disp_trans_v: Optional vertical transverse dispersivity per cell (L).

    Returns:
        A `CellProperties` object ready for use in `fit_waterloo()`.
    """
    ...


def hydrate_cell_flows(
    head: npt.NDArray[np.float64],
    water_table: npt.NDArray[np.float64],
    q_top: npt.NDArray[np.float64],
    q_bot: npt.NDArray[np.float64],
    q_vert: npt.NDArray[np.float64],
    q_well: npt.NDArray[np.float64],
    q_other: npt.NDArray[np.float64],
    q_storage: npt.NDArray[np.float64],
    has_well: npt.NDArray[np.bool_],
    face_offset: npt.NDArray[np.integer[Any]],
    face_flow: npt.NDArray[np.float64],
    face_neighbor: npt.NDArray[np.integer[Any]],
    # Optional boundary condition metadata (IFACE-based capture)
    bc_cell_ids: Optional[npt.NDArray[np.integer[Any]]] = None,
    bc_iface: Optional[npt.NDArray[np.integer[Any]]] = None,
    bc_flow: Optional[npt.NDArray[np.float64]] = None,
    bc_type_id: Optional[npt.NDArray[np.integer[Any]]] = None,
    bc_type_names: Optional[List[str]] = None,
    is_domain_boundary: Optional[npt.NDArray[np.bool_]] = None,
    has_water_table: Optional[npt.NDArray[np.bool_]] = None,
) -> CellFlows:
    """Hydrate cell flow data from NumPy arrays.

    mp3du API convention (target):

    - ``face_flow``: positive = **into** cell.
    - ``q_well``: negative = extraction, positive = injection (raw MODFLOW sign).

    The transformation from raw MODFLOW output depends on version:

    - **MODFLOW-USG / MF6** (``FLOW-JA-FACE``): raw is positive = IN.
      **Pass directly**: ``face_flow = flowja``.
    - **MODFLOW-2005 / NWT** (after directional→per-face assembly):
      result is positive = OUT. **Negate**: ``face_flow = -assembled``.

    Pass the **same** ``face_flow`` array to both ``hydrate_cell_flows()``
    and ``hydrate_waterloo_inputs()``.  No per-function negation needed.

    Never negate ``q_well``.

    Vertical flow and storage:

    - ``q_top``, ``q_bot``: total flow through the top and bottom faces
      (cell-to-cell and boundary), positive **upward** as in mod-PATH3DU.
      ``q_bot`` positive is flow into the cell from below; ``q_top``
      positive is flow out through the top, so recharge entering the top
      is negative. Used for the vertical velocity only.

    - ``q_vert``: net vertical flow **without storage**, mod-PATH3DU's
      ``(qtop - qbot) + (qtopface - qbotface)``: minus the net inflow
      through the cell's top and bottom faces, counting cell-to-cell flow
      and boundary flow routed to those faces. Pass the same ``q_vert``
      to ``hydrate_waterloo_inputs()``.
    - ``q_storage``: storage flow (L³/T) in MODFLOW's sign, positive =
      water released from storage into the cell. MODFLOW 6: ``STO-SS +
      STO-SY`` per cell (through the API, ``GWF/STO/STRGSS +
      GWF/STO/STRGSY``); MODFLOW-2005 / USG: ``STORAGE``. Zeros for steady
      state. **Do not negate.** ``fit_waterloo()`` subtracts it from
      ``q_vert``, as mod-PATH3DU does; do not also add it to ``q_vert``.

    For a cell whose budget closes, ``q_vert - q_storage`` equals
    ``sum(face_flow) + q_well + q_other`` for that cell.

    Arrays: all 1-D, one value per cell (face_*: one per face row). The
    float arrays must be float64 and the masks bool. The integer arrays
    (face_offset, face_neighbor and the bc_* ids and codes) may have any
    integer dtype; each value is checked to fit.

    See ``docs/reference/units-and-conventions.md`` for the full reference.
    """
    ...


def hydrate_waterloo_inputs(
    centers_xy: npt.NDArray[np.float64],
    radii: npt.NDArray[np.float64],
    perimeters: npt.NDArray[np.float64],
    areas: npt.NDArray[np.float64],
    q_vert: npt.NDArray[np.float64],
    q_well: npt.NDArray[np.float64],
    q_other: npt.NDArray[np.float64],
    face_offset: npt.NDArray[np.integer[Any]],
    face_vx1: npt.NDArray[np.float64],
    face_vy1: npt.NDArray[np.float64],
    face_vx2: npt.NDArray[np.float64],
    face_vy2: npt.NDArray[np.float64],
    face_length: npt.NDArray[np.float64],
    face_flow: npt.NDArray[np.float64],
    noflow_mask: npt.NDArray[np.bool_],
) -> WaterlooInputs:
    """Hydrate Waterloo velocity-fitting inputs from NumPy arrays.

    mp3du API convention (target):

    - ``face_flow``: positive = **INTO** cell — same as ``hydrate_cell_flows()``.
    - ``q_well``: raw MODFLOW sign (negative = extraction). **Do NOT negate.**

    Pass the **same** ``face_flow`` array used for ``hydrate_cell_flows()``.
    No per-function negation or sign flip is needed.

    The Waterloo method subtracts the analytic well singularity during fitting
    and adds it back during evaluation; both must use the same ``q_well`` sign.

    ``q_vert``: the same array as for ``hydrate_cell_flows()``, **without
    storage**. ``fit_waterloo()`` subtracts ``cell_flows.q_storage`` from it.
    See ``docs/reference/units-and-conventions.md`` for the full reference.

    Arrays: centers_xy has shape (n_cells, 2); the others are 1-D, one value
    per cell or per face row. The float arrays must be float64 and
    noflow_mask bool; face_offset may have any integer dtype.
    """
    ...


def build_grid(
    vertices: List[List[Tuple[float, float]]],
    centers: List[Tuple[float, float, float]],
) -> GridHandle:
    """Compile an unstructured polygon grid into a `GridHandle`.

    Args:
        vertices: For each cell, an ordered list of ``(x, y)`` vertex
            coordinates defining the cell polygon.
        centers: For each cell, a ``(x, y, z)`` tuple giving the cell
            centroid (x, y) and representative elevation (z).

    Returns:
        A `GridHandle` that can be passed to `fit_waterloo()` or
        `fit_sspa()`.  The handle is consumed (invalidated) by the
        fitting call.
    """
    ...


def fit_waterloo(
    config: WaterlooConfig,
    grid: GridHandle,
    fit_inputs: WaterlooInputs,
    cell_properties: CellProperties,
    cell_flows: CellFlows,
    top_neighbor: Optional[List[Optional[int]]] = None,
    bot_neighbor: Optional[List[Optional[int]]] = None,
    nodes_per_layer: int = 0,
) -> VelocityFieldHandle:
    """Fit the Waterloo velocity field.

    Consumes the GridHandle (it will no longer be loaded after the call).
    If the inputs are rejected with ValueError, the GridHandle is left loaded.
    Well locations are derived automatically from cell_flows.has_well
    and the grid cell centres.

    Vertical connectivity: top_neighbor and bot_neighbor give, for each
    cell, the id of the cell above and below it (None at the top or bottom
    of the model; both default to None for every cell). nodes_per_layer is
    the number of cells per layer, 0 for a single layer; it must divide the
    number of cells.

    Sign conventions: fit_inputs must use face_flow positive = INTO cell
    (same array as hydrate_cell_flows; q_well = raw MODFLOW sign).
    See hydrate_waterloo_inputs() and docs/reference/units-and-conventions.md.

    Storage: ``cell_flows.q_storage`` is subtracted from the vertical term
    ``q_vert`` of both ``fit_inputs`` and ``cell_flows``, as mod-PATH3DU
    2.1.9 does (``qvert = ... - qsto``). Pass storage only in
    ``q_storage``, in MODFLOW's sign; do not also add it to ``q_vert``.
    Before 0.1.2, ``q_storage`` was accepted but not used.

    Raises:
        ValueError: If the inputs do not match the grid, or a cell cannot be
            fitted: fewer than 3 faces, face arrays of different lengths, or
            a no-flow face index out of range. The message names the cell.
            (Before 0.1.3 such a cell ended the Python process when a
            particle first entered it.)
    """
    ...


def run_simulation(
    config: SimulationConfig,
    velocity_field: VelocityFieldHandle,
    particles: List[ParticleStart],
    parallel: bool = True,
) -> List[TrajectoryResult]:
    """Run particle tracking on a fitted velocity field.

    Well capture is controlled by capture.capture_radius in the
    SimulationConfig:
      - Omitted / null: capture immediately on cell entry (strong sink).
      - A positive number (e.g. 0.5): capture only when within that
        distance of the cell centre (weak sink).

    A particle whose cell_id is not a cell of the field raises ValueError.

    Dispersivity comes from exactly one place: the configuration's
    dispersion block (alpha_l, alpha_th, alpha_tv, the same in every cell),
    or the per-cell arrays given to hydrate_cell_properties() or
    hydrate_sspa_inputs() (disp_long, disp_trans_h, disp_trans_v). With
    dispersion on, ValueError is raised before any particle is tracked if
    it is given both ways or neither, if the Ito method is given per-cell
    values that differ between cells (use Gsde), or if the vertical
    transverse dispersivity is not 0 with an SSP&A field. With dispersion
    off ("method": "None"), per-cell arrays are not used, and a
    UserWarning says so unless every value is 0.
    """
    ...
