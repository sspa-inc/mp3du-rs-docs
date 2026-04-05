# Complete Configuration Example

A fully-specified `SimulationConfig` JSON exercising all available options, including GSDE dispersion and retardation.

## Configuration

```json
--8<-- "docs/examples/configs/complete.json"
```

## Field Reference

### Top-Level Fields

| Field | Value | Description |
|-------|-------|-------------|
| `velocity_method` | `"Waterloo"` | Waterloo velocity interpolation method |
| `solver` | `"DormandPrince"` | Dormand-Prince 5(4) adaptive solver |
| `direction` | `1.0` | Forward tracking (in the direction of flow) |
| `initial_dt` | `1.0` | Initial time step of 1 day |
| `max_dt` | `100.0` | Maximum time step of 100 days |
| `retardation_enabled` | `true` | Retardation active — uses per-cell retardation factors |

### Adaptive Stepping

| Field | Value | Description |
|-------|-------|-------------|
| `tolerance` | `1e-6` | Local error tolerance for step acceptance |
| `safety` | `0.9` | Safety factor for step-size prediction |
| `alpha` | `0.2` | PI controller exponent |
| `min_scale` | `0.2` | Minimum step-size scale factor |
| `max_scale` | `5.0` | Maximum step-size scale factor |
| `max_rejects` | `10` | Maximum consecutive rejected steps |
| `min_dt` | `1e-10` | Absolute minimum time step (days) |
| `euler_dt` | `1.0` | Fixed step size for Euler solver |

### Dispersion

| Field | Value | Description |
|-------|-------|-------------|
| `method` | `"Gsde"` | Generalised Stochastic Differential Equation |
| `alpha_l` | `10.0` | Longitudinal dispersivity (length units) |
| `alpha_th` | `1.0` | Transverse horizontal dispersivity |
| `alpha_tv` | `0.1` | Transverse vertical dispersivity |

### Capture (Termination Criteria)

| Field | Value | Description |
|-------|-------|-------------|
| `max_time` | `365250.0` | Maximum tracking time — 1000 years in days |
| `max_steps` | `1000000` | Maximum number of integration steps |
| `stagnation_velocity` | `1e-12` | Velocity threshold for stagnation detection |
| `stagnation_limit` | `100` | Consecutive stagnant steps before termination |

## Notes

!!! tip
    Most simulations do not need all options. Start with the [minimal configuration](minimal-config.md) and add options as needed.

!!! info "Dispersion Methods"
    Three dispersion methods are available: `"None"` (advection only), `"Gsde"` (Generalised SDE), and `"Ito"` (Ito formulation). See [Dispersion Methods](../reference/dispersion-methods.md) for the mathematical background.

## See Also

- [Minimal Configuration](minimal-config.md) — Start here
- [Schema Reference](../reference/schema-reference.md) — Full property contract with constraints
- [Dispersion Theory](../concepts/dispersion-theory.md) — Mathematical formulations
- [Adaptive Stepping](../concepts/adaptive-stepping.md) — Step-size control explained
