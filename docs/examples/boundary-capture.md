# Boundary Capture Example

End-to-end backward tracking with CHD boundary capture using IFACE.

This example is based on Example3 from the mod-PATH3DU test suite — a
MODFLOW-USG model with constant-head boundary conditions.

---

## Overview

| Property | Value |
|----------|-------|
| Model | MODFLOW-USG, single-layer |
| Boundary conditions | CONSTANT HEAD (CHD) on selected cells |
| IFACE | 2 (side face — distributed BC) |
| Tracking direction | Backward (`-1.0`) |
| Expected termination | `CapturedByBoundary` with reason `"Internal sink/source: CONSTANT HEAD"` |

---

## Python Script

```python
import json
import sys
from pathlib import Path

import numpy as np
import shapefile  # pyshp

import mp3du

# Add scripts directory for the IFACE routing helper
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from mp3du_iface_routing import route_iface_bc_flows

# ------------------------------------------------------------------
# 1. Paths
# ------------------------------------------------------------------
example_dir = Path(__file__).resolve().parent
data_dir = example_dir / "data"

# ------------------------------------------------------------------
# 2. Load grid geometry from shapefiles
# ------------------------------------------------------------------
sf = shapefile.Reader(str(data_dir / "grid"))
vertices = []
for shape in sf.shapes():
    pts = [(p[0], p[1]) for p in shape.points[:-1]]  # drop closing vertex
    vertices.append(pts)

n_cells = len(vertices)
centroids = [(np.mean([p[0] for p in v]), np.mean([p[1] for p in v]), 50.0)
             for v in vertices]

grid = mp3du.build_grid(vertices, centroids)
print(f"Grid: {grid.n_cells()} cells")

# ------------------------------------------------------------------
# 3. Load MODFLOW cell data (properties, flows, etc.)
# ------------------------------------------------------------------
# ... load your per-cell arrays from MODFLOW output ...
# (head, water_table, q_top, q_bot, q_vert, q_well, q_other, q_storage,
#  has_well, face_offset, face_flow, face_neighbor, top, bot, porosity, etc.)

# ------------------------------------------------------------------
# 4. Assemble boundary condition arrays with IFACE routing
# ------------------------------------------------------------------
# Extract CHD flows from MODFLOW CBC output
chd_data = [...]  # your CBC extraction — list of (node, q) tuples

bc_cell_ids = []
bc_iface_arr = []
bc_flow_arr = []
bc_type_id_arr = []
bc_type_names = ["CONSTANT HEAD"]

for node, q in chd_data:
    bc_cell_ids.append(int(node) - 1)   # convert to 0-based
    bc_iface_arr.append(2)               # CHD → side face
    bc_flow_arr.append(float(q))         # raw MODFLOW sign
    bc_type_id_arr.append(0)             # index into bc_type_names

# Use the routing helper to compute flow contributions
routed = route_iface_bc_flows(
    n_cells=n_cells,
    bc_cell_ids=np.array(bc_cell_ids, dtype=np.int64),
    bc_iface=np.array(bc_iface_arr, dtype=np.int32),
    bc_flow=np.array(bc_flow_arr, dtype=np.float64),
)
# routed["q_well"], routed["q_other"], routed["q_top"], routed["q_bot"]
# Add these to your base flow arrays before hydration.

# ------------------------------------------------------------------
# 5. Hydrate cell flows with boundary metadata
# ------------------------------------------------------------------
cell_flows = mp3du.hydrate_cell_flows(
    head=head_array,
    water_table=wt_array,
    q_top=q_top_array + routed["q_top"],       # add BC contributions
    q_bot=q_bot_array + routed["q_bot"],
    q_vert=q_vert_array,
    q_well=q_well_array + routed["q_well"],
    q_other=q_other_array + routed["q_other"],
    q_storage=q_storage_array,
    has_well=has_well_array,
    face_offset=face_offset,
    face_flow=face_flow_array,
    face_neighbor=face_nbr_array,
    # Boundary metadata for IFACE-based capture
    bc_cell_ids=np.array(bc_cell_ids, dtype=np.int64),
    bc_iface=np.array(bc_iface_arr, dtype=np.int32),
    bc_flow=np.array(bc_flow_arr, dtype=np.float64),
    bc_type_id=np.array(bc_type_id_arr, dtype=np.int32),
    bc_type_names=bc_type_names,
)

# ------------------------------------------------------------------
# 6. Hydrate Waterloo inputs to fit the velocity field
# ------------------------------------------------------------------
waterloo_inputs = mp3du.hydrate_waterloo_inputs(
    centers_xy=np.array([[c[0], c[1]] for c in centroids]),
    radii=radii_array,
    perimeters=perimeters_array,
    areas=areas_array,
    q_vert=q_vert_array,
    q_well=q_well_array + routed["q_well"],
    q_other=q_other_array + routed["q_other"],
    face_offset=face_offset,
    face_vx1=face_vx1, face_vy1=face_vy1,
    face_vx2=face_vx2, face_vy2=face_vy2,
    face_length=face_length,
    face_flow=-face_flow_array,    # NEGATE for Waterloo convention
    noflow_mask=noflow_mask,
)

waterloo_cfg = mp3du.WaterlooConfig(order_of_approx=35, n_control_points=122)
field = mp3du.fit_waterloo(waterloo_cfg, grid, waterloo_inputs, cell_props, cell_flows)

# ------------------------------------------------------------------
# 7. Configure and run backward tracking
# ------------------------------------------------------------------
config_dict = {
    "velocity_method": "Waterloo",
    "solver": "DormandPrince",
    "direction": -1.0,       # backward tracking
    "initial_dt": 1.0,
    "max_dt": 1000.0,
    "retardation_enabled": False,
    "adaptive": {
        "tolerance": 1e-6, "safety": 0.9, "alpha": 0.2,
        "min_scale": 0.2, "max_scale": 5.0, "max_rejects": 10,
        "min_dt": 1e-10, "euler_dt": 0.1,
    },
    "dispersion": {"method": "None"},
    "capture": {
        "max_time": 1e10,
        "max_steps": 500000,
        "stagnation_velocity": 1e-14,
        "stagnation_limit": 200,
    },
}
config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))

particles = [
    mp3du.ParticleStart(id=i, x=px, y=py, z=pz, cell_id=cid, initial_dt=1.0)
    for i, (px, py, pz, cid) in enumerate(particle_starts)
]

results = mp3du.run_simulation(config, field, particles, parallel=True)

# ------------------------------------------------------------------
# 8. Inspect results
# ------------------------------------------------------------------
for r in results:
    print(f"Particle {r.particle_id}: {r.final_status} — {r.termination_reason}")
    # Expected: "CapturedByBoundary — Internal sink/source: CONSTANT HEAD"
```

---

## Expected Output

For a model where all particles originate downstream of CHD cells with
backward tracking, every particle should terminate at a CHD boundary:

```text
Particle 0: CapturedByBoundary — Internal sink/source: CONSTANT HEAD
Particle 1: CapturedByBoundary — Internal sink/source: CONSTANT HEAD
...
```

---

## Key Points

1. **IFACE 2** routes CHD flows to `q_other` (distributed side-face BC).
2. **Backward tracking** (`direction: -1.0`) traces particles upstream to
   their source.
3. The `route_iface_bc_flows()` helper handles IFACE-to-flow-bucket routing
   and sign conventions automatically.
4. All `bc_*` arrays are passed to `hydrate_cell_flows()` for both velocity
   field reconstruction **and** capture metadata.
5. The `termination_reason` field provides the human-readable BC type name.

---

## See Also

- [IFACE & Boundary Capture](../concepts/iface-boundary-capture.md) — Conceptual guide
- [IFACE Flow Routing](../reference/iface-flow-routing.md) — Technical spec
- [Running Simulations](../guides/running-simulations.md#hydrating-boundary-conditions) — Workflow guide
