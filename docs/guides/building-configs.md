# Building Configurations

How to create a `SimulationConfig` JSON for mod-PATH3DU simulations.

## Configuration Overview

Every simulation is driven by a `SimulationConfig` JSON object that controls the solver, dispersion model, adaptive stepping, capture criteria, and tracking direction. The configuration is loaded in Python via:

```python
import json
import mp3du

config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))
config.validate()  # raises on invalid config
```

See the [Schema Reference](../reference/schema-reference.md) for the complete contract.

## Minimal vs. Complete Configuration

=== "Minimal"

    The smallest valid configuration — uses advection-only tracking with sensible defaults:

    ```json
    {
      "velocity_method": "Waterloo",
      "solver": "DormandPrince",
      "direction": 1.0,
      "initial_dt": 1.0,
      "max_dt": 1000.0,
      "retardation_enabled": false,
      "adaptive": {
        "tolerance": 1e-6,
        "safety": 0.9,
        "alpha": 0.2,
        "min_scale": 0.2,
        "max_scale": 5.0,
        "max_rejects": 10,
        "min_dt": 1e-10,
        "euler_dt": 0.1
      },
      "dispersion": {
        "method": "None"
      },
      "capture": {
        "max_time": 365000.0,
        "max_steps": 1000000,
        "stagnation_velocity": 1e-12,
        "stagnation_limit": 100
      }
    }
    ```

=== "Complete (with GSDE dispersion)"

    A fully-specified configuration with GSDE dispersion enabled:

    ```json
    {
      "velocity_method": "Waterloo",
      "solver": "DormandPrince",
      "direction": 1.0,
      "initial_dt": 0.5,
      "max_dt": 500.0,
      "retardation_enabled": true,
      "adaptive": {
        "tolerance": 1e-7,
        "safety": 0.9,
        "alpha": 0.2,
        "min_scale": 0.2,
        "max_scale": 5.0,
        "max_rejects": 20,
        "min_dt": 1e-12,
        "euler_dt": 0.01
      },
      "dispersion": {
        "method": "Gsde",
        "alpha_l": 10.0,
        "alpha_th": 1.0,
        "alpha_tv": 0.1
      },
      "capture": {
        "max_time": 3650000.0,
        "max_steps": 5000000,
        "stagnation_velocity": 1e-14,
        "stagnation_limit": 200,
        "capture_radius": 0.5,
        "face_epsilon": 1e-6
      }
    }
    ```

## Required Fields

All top-level fields and most nested fields are required. The capture block may omit `capture.capture_radius` (strong-sink behaviour) and the advanced `capture.face_epsilon` override. Every other field shown in the minimal examples must be explicitly specified.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `velocity_method` | string | `"Waterloo"` | Velocity interpolation method |
| `solver` | string | One of 6 solvers | Runge–Kutta solver variant |
| `direction` | number | `1.0` or `-1.0` | Forward or backward tracking |
| `initial_dt` | number | > 0 | Initial time step |
| `max_dt` | number | > 0 | Maximum time step |
| `retardation_enabled` | boolean | — | Enable retardation factors |
| `adaptive` | object | See below | Adaptive stepping parameters |
| `dispersion` | object | See below | Dispersion configuration |
| `capture` | object | See below | Termination criteria |

### Solver

Choose one of the six available solvers:

| Solver | Order | Adaptive | Best for |
|--------|-------|----------|----------|
| `Euler` | 1 | No | Quick tests, debugging |
| `Rk4StepDoubling` | 4 | Yes | General purpose |
| `DormandPrince` | 4/5 | Yes | **Recommended default** |
| `CashKarp` | 4/5 | Yes | Stiff-ish problems |
| `VernerRobust` | 6/7 | Yes | High accuracy |
| `VernerEfficient` | 6/7 | Yes | High accuracy, fewer stages |

See [Solver Methods](../reference/solver-methods.md) for mathematical details.

## Adaptive Stepping

```json
"adaptive": {
  "tolerance": 1e-6,       // (1)!
  "safety": 0.9,           // (2)!
  "alpha": 0.2,            // (3)!
  "min_scale": 0.2,        // (4)!
  "max_scale": 5.0,        // (5)!
  "max_rejects": 10,       // (6)!
  "min_dt": 1e-10,         // (7)!
  "euler_dt": 0.1          // (8)!
}
```

1. **tolerance** — Error threshold for step acceptance. Smaller = more accurate, slower.
2. **safety** — Multiplier applied to the optimal step size (typically 0.8–0.95). Prevents frequent rejections.
3. **alpha** — Exponent in the step-scaling formula. For a 5th-order pair, use 0.2.
4. **min_scale** — Minimum step-size reduction factor. Step can shrink to at most `min_scale × h`.
5. **max_scale** — Maximum step-size growth factor. Step can grow to at most `max_scale × h`.
6. **max_rejects** — Maximum consecutive rejected steps before the solver gives up.
7. **min_dt** — Absolute minimum time step. If the solver needs smaller, it raises an error.
8. **euler_dt** — Fixed step size used only by the Euler solver.

See [Adaptive Stepping](../concepts/adaptive-stepping.md) for the mathematical background.

## Dispersion

=== "None (advection only)"

    ```json
    "dispersion": {
      "method": "None"
    }
    ```

=== "GSDE"

    ```json
    "dispersion": {
      "method": "Gsde",
      "alpha_l": 10.0,    // (1)!
      "alpha_th": 1.0,    // (2)!
      "alpha_tv": 0.1     // (3)!
    }
    ```

    1. **alpha_l** — Longitudinal dispersivity (spreading along flow). Units match model length units.
    2. **alpha_th** — Horizontal transverse dispersivity (spreading perpendicular to flow, in the horizontal plane).
    3. **alpha_tv** — Vertical transverse dispersivity (spreading perpendicular to flow, in the vertical direction).

=== "Ito"

    ```json
    "dispersion": {
      "method": "Ito",
      "alpha_l": 10.0,
      "alpha_th": 1.0,
      "alpha_tv": 0.1
    }
    ```

See [Dispersion Theory](../concepts/dispersion-theory.md) for the mathematical formulation and [Dispersion Methods](../reference/dispersion-methods.md) for the parameter specification.

## Capture (Termination Criteria)

```json
"capture": {
  "max_time": 365000.0,           // (1)!
  "max_steps": 1000000,           // (2)!
  "stagnation_velocity": 1e-12,   // (3)!
  "stagnation_limit": 100,        // (4)!
  "capture_radius": 0.5,          // (5)!
  "face_epsilon": 1e-6            // (6)!
}
```

1. **max_time** — Maximum simulation time. Particle tracking stops after this many time units.
2. **max_steps** — Maximum number of integration steps per particle.
3. **stagnation_velocity** — If the velocity magnitude falls below this threshold, the particle is considered stagnant.
4. **stagnation_limit** — Number of consecutive stagnant steps before the particle is terminated.
5. **capture_radius** — *(optional)* Distance from the well centre (cell centre) within which a particle is captured. Omit this field to capture particles as soon as they enter a well cell. Only applies to IFACE 0 (well) cells.
6. **face_epsilon** — *(optional, advanced)* Tolerance for top/bottom face proximity checks during IFACE-based capture. Default: `1e-6`. Most users will never need to change this.

### Capture Behaviour

Particle capture is controlled by the boundary condition metadata passed to
`hydrate_cell_flows()`. Each IFACE value triggers a different capture check:

| IFACE | Face | Capture Check | Config Field |
|-------|------|--------------|-------------|
| 0 (well) | Cell centre | Distance from cell centre ≤ `capture_radius` | `capture_radius` |
| 2 (side face) | Side | Immediate on cell entry + flow sign check | — |
| 5 (bottom face) | Bottom | $z < \texttt{face\_epsilon}$ + flow sign check | `face_epsilon` |
| 6 (top face) | Top | $z > 1 - \texttt{face\_epsilon}$ + flow sign + $v_z$ direction | `face_epsilon` |
| 7 (internal) | Internal | Immediate on cell entry + flow sign check | — |

The capture priority chain (highest to lowest):

1. **Domain boundary** — `is_domain_boundary = True` (excludes IFACE 0 cells)
2. **InternalWell** — IFACE 0 (well capture with `capture_radius`)
3. **Internal** — IFACE 2 or 7 (immediate on cell entry)
4. **TopFace / BottomFace** — IFACE 6 or 5 (face proximity check)

!!! tip "Legacy `has_well` behaviour"
    If no `bc_*` arrays are provided, capture falls back to the legacy
    `has_well` mechanism. When `bc_*` arrays **are** present, `has_well` is
    ignored for cells that have boundary entries.

!!! info "Advanced: `face_epsilon`"
    The `face_epsilon` parameter controls how close a particle must be to
    the top or bottom cell face before capture triggers. The default `1e-6`
    works well for virtually all models. Decrease it only if particles are
    being incorrectly captured too far from the face, or increase it if
    particles are "leaking" through face boundaries.

## Validation

Before running a simulation, you can validate a configuration against the JSON Schema:

```python
import json
import jsonschema

with open("mp3du-rs/python/mp3du_schema.json") as f:
    schema = json.load(f)

config_dict = {
    "velocity_method": "Waterloo",
    "solver": "DormandPrince",
    "direction": 1.0,
    "initial_dt": 1.0,
    "max_dt": 1000.0,
    "retardation_enabled": False,
    "adaptive": {
        "tolerance": 1e-6,
        "safety": 0.9,
        "alpha": 0.2,
        "min_scale": 0.2,
        "max_scale": 5.0,
        "max_rejects": 10,
        "min_dt": 1e-10,
        "euler_dt": 0.1,
    },
    "dispersion": {"method": "None"},
    "capture": {
        "max_time": 365000.0,
        "max_steps": 1000000,
        "stagnation_velocity": 1e-12,
        "stagnation_limit": 100,
    },
}

jsonschema.validate(instance=config_dict, schema=schema)
print("Configuration is valid!")
```

You can also validate after constructing a `SimulationConfig`:

```python
config = mp3du.SimulationConfig.from_json(json.dumps(config_dict))
config.validate()  # raises if invalid
```

## Common Mistakes

!!! warning "Direction must be exactly `1.0` or `-1.0`"
    The schema uses an **enum** constraint, not a range. Integer values like `1` or `-1` are rejected. Fractional values like `0.5` are rejected. Use exactly `1.0` (forward) or `-1.0` (backward).

!!! warning "Solver names are case-sensitive"
    `"dormandprince"` and `"dormand_prince"` are invalid. Use the exact enum values: `Euler`, `Rk4StepDoubling`, `DormandPrince`, `CashKarp`, `VernerRobust`, `VernerEfficient`.

!!! warning "All `adaptive` fields are required"
    Even if you use a non-adaptive solver like Euler, the `adaptive` block and all its fields must be present. Use the defaults from the minimal example above.

!!! warning "Dispersion `alpha_*` values must be ≥ 0"
    Negative dispersivity values are physically meaningless and will be rejected by the schema. Use `0.0` if a particular dispersivity component is not needed.

!!! warning "`additional_properties` is false"
    The schema disallows extra fields. Typos like `"solver_name"` instead of `"solver"` will cause a validation error.
