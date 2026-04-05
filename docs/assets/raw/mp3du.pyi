"""Type stubs for the mp3du Rust particle tracker."""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import numpy.typing as npt


def version() -> str: ...


class WaterlooConfig:
    def __init__(self, order_of_approx: int = 35, n_control_points: int = 122) -> None: ...
    @property
    def order_of_approx(self) -> int: ...
    @property
    def n_control_points(self) -> int: ...


class SimulationConfig:
    @staticmethod
    def from_json(json_str: str) -> "SimulationConfig": ...
    def to_json(self) -> str: ...
    def validate(self) -> None: ...


class ParticleStart:
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
    particle_id: int
    final_status: str
    termination_reason: str
    def to_records(self) -> List[Dict[str, Any]]: ...
    def __len__(self) -> int: ...


class GridHandle:
    def is_loaded(self) -> bool: ...
    def n_cells(self) -> int: ...


class WaterlooFieldHandle:
    def is_loaded(self) -> bool: ...
    def method_name(self) -> str: ...
    def n_cells(self) -> int: ...


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
    def disp_long(self) -> List[float]: ...
    @property
    def disp_trans_h(self) -> List[float]: ...
    @property
    def disp_trans_v(self) -> List[float]: ...
    def n_cells(self) -> int: ...


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
    disp_long: npt.NDArray[np.float64],
    disp_trans_h: npt.NDArray[np.float64],
    disp_trans_v: npt.NDArray[np.float64],
) -> CellProperties: ...


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
    face_offset: npt.NDArray[np.uint64],
    face_flow: npt.NDArray[np.float64],
    face_neighbor: npt.NDArray[np.int64],
    # Optional boundary condition metadata (IFACE-based capture)
    bc_cell_ids: Optional[npt.NDArray[np.int64]] = None,
    bc_iface: Optional[npt.NDArray[np.int32]] = None,
    bc_flow: Optional[npt.NDArray[np.float64]] = None,
    bc_type_id: Optional[npt.NDArray[np.int32]] = None,
    bc_type_names: Optional[List[str]] = None,
    is_domain_boundary: Optional[npt.NDArray[np.bool_]] = None,
    has_water_table: Optional[npt.NDArray[np.bool_]] = None,
) -> CellFlows:
    """Hydrate cell flow data from NumPy arrays.

    Sign conventions (pass raw MODFLOW values — no negation):
      - face_flow: positive = out of cell (MODFLOW CBC convention).
      - q_well: negative = extraction, positive = injection (raw MODFLOW sign).

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
    face_offset: npt.NDArray[np.uint64],
    face_vx1: npt.NDArray[np.float64],
    face_vy1: npt.NDArray[np.float64],
    face_vx2: npt.NDArray[np.float64],
    face_vy2: npt.NDArray[np.float64],
    face_length: npt.NDArray[np.float64],
    face_flow: npt.NDArray[np.float64],
    noflow_mask: npt.NDArray[np.bool_],
) -> WaterlooInputs:
    """Hydrate Waterloo velocity-fitting inputs from NumPy arrays.

    Sign conventions (CRITICAL — differs from hydrate_cell_flows):
      - face_flow: positive = INTO cell (Waterloo convention).
        Negate MODFLOW CBC output: ``waterloo_face_flow = -modflow_face_flow``.
      - q_well: raw MODFLOW sign (negative = extraction). Do NOT negate.
        The Waterloo method subtracts the analytic well singularity
        during fitting and adds it back during evaluation; both must
        use the same sign.

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
) -> WaterlooFieldHandle:
    """Fit the Waterloo velocity field.

    Consumes the GridHandle (it will no longer be loaded after the call).
    Well locations are derived automatically from cell_flows.has_well
    and the grid cell centres.

    Sign conventions: fit_inputs must use Waterloo conventions
    (face flow positive = into cell; q_well = raw MODFLOW sign).
    See hydrate_waterloo_inputs() and docs/reference/units-and-conventions.md.
    """
    ...


def run_simulation(
    config: SimulationConfig,
    velocity_field: WaterlooFieldHandle,
    particles: List[ParticleStart],
    parallel: bool = True,
) -> List[TrajectoryResult]:
    """Run particle tracking on a fitted velocity field.

    Well capture is controlled by capture.capture_radius in the
    SimulationConfig:
      - Omitted / null: capture immediately on cell entry (strong sink).
      - A positive number (e.g. 0.5): capture only when within that
        distance of the cell centre (weak sink).
    """
    ...
