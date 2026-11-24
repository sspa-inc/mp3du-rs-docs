"""Type stubs for the mp3du Rust particle tracker."""

from typing import Any, Dict, List, Optional, Tuple, final

import numpy as np
import numpy.typing as npt

__all__ = [
    "version",
    "hydrate_cell_properties",
    "hydrate_cell_flows",
    "hydrate_waterloo_inputs",
    "hydrate_sspa_inputs",
    "build_grid",
    "fit_waterloo",
    "fit_sspa",
    "run_simulation",
    "WaterlooConfig",
    "SspaConfig",
    "SimulationConfig",
    "ParticleStart",
    "TrajectoryResult",
    "GridHandle",
    "VelocityFieldHandle",
    "WaterlooFieldHandle",
    "CellProperties",
    "CellFlows",
    "WaterlooInputs",
    "SspaInputs",
]


def version() -> str: ...


@final
class WaterlooConfig:
    def __new__(cls, order_of_approx: int = 35, n_control_points: int = 122) -> WaterlooConfig: ...
    @property
    def order_of_approx(self) -> int: ...
    @property
    def n_control_points(self) -> int: ...


@final
class SimulationConfig:
    @staticmethod
    def from_json(json_str: str) -> "SimulationConfig":
        """Create from a JSON string.

        Raises ValueError for an invalid configuration or an unknown key, and
        issues a UserWarning for settings that are valid but probably not
        intended.
        """
        ...
    def to_json(self) -> str: ...
    def validate(self) -> None: ...


@final
class ParticleStart:
    id: int
    x: float
    y: float
    z: float
    cell_id: int
    initial_dt: float
    def __new__(
        cls,
        id: int,
        x: float,
        y: float,
        z: float,
        cell_id: int,
        initial_dt: float,
    ) -> ParticleStart: ...


@final
class TrajectoryResult:
    @property
    def particle_id(self) -> int: ...
    @property
    def final_status(self) -> str: ...
    @property
    def termination_reason(self) -> str: ...
    def to_records(self) -> List[Dict[str, Any]]:
        """One dict per step, with the keys ``step``, ``time``, ``x``, ``y``,
        ``z``, ``vx``, ``vy``, ``vz``, ``cell_id`` and ``dt``."""
        ...
    def __len__(self) -> int: ...


@final
class GridHandle:
    def __new__(cls) -> GridHandle: ...
    def is_loaded(self) -> bool: ...
    def n_cells(self) -> int: ...


@final
class VelocityFieldHandle:
    def __new__(cls) -> VelocityFieldHandle: ...
    def is_loaded(self) -> bool: ...
    def method_name(self) -> str: ...
    def n_cells(self) -> int: ...
    def velocity_at(self, x: float, y: float, z: float) -> Tuple[float, float, float]: ...


# Alias — fit_sspa() and fit_waterloo() both return the same handle type.
WaterlooFieldHandle = VelocityFieldHandle


@final
class SspaConfig:
    def __new__(cls, search_radius: float = ..., krig_offset: float = ...) -> SspaConfig: ...
    @property
    def search_radius(self) -> float: ...
    @property
    def krig_offset(self) -> float: ...


@final
class SspaInputs:
    def n_cells(self) -> int: ...
    def __len__(self) -> int: ...
    @property
    def heads(self) -> List[float]: ...
    @property
    def hydraulic_conductivity(self) -> List[float]: ...
    @property
    def hhk(self) -> List[float]: ...
    @property
    def porosity(self) -> List[float]: ...
    @property
    def well_mask(self) -> List[bool]: ...
    @property
    def disp_long(self) -> Optional[List[float]]:
        """Longitudinal dispersivity per cell, or None if not given per cell."""
        ...
    @property
    def disp_trans_h(self) -> Optional[List[float]]:
        """Horizontal transverse dispersivity per cell, or None if not given per cell."""
        ...
    @property
    def disp_trans_v(self) -> Optional[List[float]]:
        """Vertical transverse dispersivity per cell, or None if not given per cell."""
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
    """Hydrate SSP&A field inputs from NumPy arrays (one value per cell).

    Exactly one of hydraulic_conductivity or hhk must be provided.

    Dispersivity is given in one of two ways, never both:

    - per cell: all three of disp_long, disp_trans_h and disp_trans_v, with
      alpha_l, alpha_th and alpha_tv left out of the configuration's
      dispersion block (for one value everywhere, fill the arrays with it,
      for example numpy.full(n, 10.0));
    - in the configuration: alpha_l, alpha_th and alpha_tv in the dispersion
      block, the same in every cell, with these three arrays left out.

    Giving only one or two of the arrays raises ValueError here; with
    dispersion on, run_simulation() raises ValueError for dispersivity given
    both ways, or neither. The SSP&A field is two-dimensional, so
    disp_trans_v (or alpha_tv) must be 0 in a run with dispersion.
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


@final
class CellProperties:
    @property
    def top(self) -> List[float]: ...
    @property
    def bot(self) -> List[float]: ...
    @property
    def porosity(self) -> List[float]: ...
    @property
    def retardation(self) -> List[float]: ...
    @property
    def hhk(self) -> List[float]: ...
    @property
    def vhk(self) -> List[float]: ...
    @property
    def disp_long(self) -> Optional[List[float]]:
        """Longitudinal dispersivity per cell, or None if not given per cell."""
        ...
    @property
    def disp_trans_h(self) -> Optional[List[float]]:
        """Horizontal transverse dispersivity per cell, or None if not given per cell."""
        ...
    @property
    def disp_trans_v(self) -> Optional[List[float]]:
        """Vertical transverse dispersivity per cell, or None if not given per cell."""
        ...
    def n_cells(self) -> int: ...


@final
class CellFlows:
    @property
    def head(self) -> List[float]: ...
    @property
    def water_table(self) -> List[float]: ...
    @property
    def q_top(self) -> List[float]: ...
    @property
    def q_bot(self) -> List[float]: ...
    @property
    def q_vert(self) -> List[float]: ...
    @property
    def q_well(self) -> List[float]: ...
    @property
    def q_other(self) -> List[float]: ...
    @property
    def q_storage(self) -> List[float]: ...
    @property
    def has_well(self) -> List[bool]: ...
    @property
    def face_offset(self) -> List[int]: ...
    @property
    def face_flow(self) -> List[float]: ...
    @property
    def face_neighbor(self) -> List[Optional[int]]: ...
    def n_cells(self) -> int: ...


@final
class WaterlooInputs:
    def n_cells(self) -> int: ...
    def __len__(self) -> int: ...


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
    """Hydrate per-cell properties from NumPy arrays (one value per cell, in
    cell-id order).

    Dispersivity is given in one of two ways, never both:

    - per cell: all three of disp_long, disp_trans_h and disp_trans_v
      (alpha_L, alpha_TH and alpha_TV, in length units), with alpha_l,
      alpha_th and alpha_tv left out of the configuration's dispersion block.
      For one value everywhere, fill the arrays with it, for example
      numpy.full(n, 10.0);
    - in the configuration: alpha_l, alpha_th and alpha_tv in the dispersion
      block, the same in every cell, with these three arrays left out.

    Giving only one or two of the arrays raises ValueError here; with
    dispersion on, run_simulation() raises ValueError for dispersivity given
    both ways, or neither. Without dispersion the arrays are not used, and
    run_simulation() issues a UserWarning saying so unless every value is 0.
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

    Sign conventions (pass raw MODFLOW values — no negation):
      - face_flow: positive = into cell (MODFLOW-USG / MF6 convention).
      - q_well: negative = extraction, positive = injection (raw MODFLOW sign).
      - q_top, q_bot: total flow through the top and bottom faces
        (cell-to-cell and boundary), positive UPWARD as in mod-PATH3DU:
        q_bot positive = into the cell from below; q_top positive = out
        through the top, so recharge entering the top is negative.
        Used for the vertical velocity only.
      - q_vert: net vertical flow WITHOUT storage, mod-PATH3DU's
        (qtop - qbot) + (qtopface - qbotface): minus the net inflow through
        the top and bottom faces, cell-to-cell and boundary flows alike.
        Pass the same q_vert to hydrate_waterloo_inputs.
      - q_storage: storage flow, L^3/T, MODFLOW's sign: positive = water
        released from storage into the cell. MODFLOW 6: STO-SS + STO-SY
        (API: GWF/STO/STRGSS + GWF/STO/STRGSY); MODFLOW-2005/USG: STORAGE.
        Zeros for steady state. fit_waterloo subtracts it from q_vert, as
        mod-PATH3DU does; do not also add it to q_vert.

    For a cell whose budget closes, q_vert - q_storage equals
    sum(face_flow) + q_well + q_other for that cell.

    Arrays: all 1-D, one value per cell (face_*: one per face row). The
    float arrays must be float64 and the masks bool. The integer arrays
    (face_offset, face_neighbor and the bc_* ids and codes) may have any
    integer dtype; each value is checked to fit.

    See docs/reference/units-and-conventions.md for the full reference.
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

    Sign conventions (same as hydrate_cell_flows):
      - face_flow: positive = INTO cell.
        Pass the SAME face_flow array as hydrate_cell_flows — no negation.
      - q_well: raw MODFLOW sign (negative = extraction). Do NOT negate.
        The Waterloo method subtracts the analytic well singularity
        during fitting and adds it back during evaluation; both must
        use the same sign.
      - q_vert: the same array as for hydrate_cell_flows, WITHOUT storage.
        fit_waterloo subtracts cell_flows.q_storage from it.

    Arrays: centers_xy has shape (n_cells, 2); the others are 1-D, one value
    per cell or per face row. The float arrays must be float64 and
    noflow_mask bool; face_offset may have any integer dtype.

    See docs/reference/units-and-conventions.md for the full reference.
    """
    ...


def build_grid(
    vertices: List[List[Tuple[float, float]]],
    centers: List[Tuple[float, float, float]],
) -> GridHandle: ...


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

    Storage: cell_flows.q_storage is subtracted from the vertical term
    q_vert of both fit_inputs and cell_flows, as mod-PATH3DU 2.1.9 does
    (qvert = ... - qsto). Pass storage only in q_storage, in MODFLOW's
    sign; do not also add it to q_vert.
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
