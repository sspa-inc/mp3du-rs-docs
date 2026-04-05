# Minimal Valid Configuration

The smallest valid `SimulationConfig` JSON for mod-PATH3DU. Every required field is present; all optional fields are omitted or set to their simplest valid value.

## Configuration

```json
--8<-- "docs/examples/configs/minimal.json"
```

## Field Descriptions

| Field | Value | Why |
|-------|-------|-----|
| `velocity_method` | `"Waterloo"` | The only supported velocity interpolation method |
| `solver` | `"DormandPrince"` | Recommended default — adaptive 5th-order Runge-Kutta with good accuracy/cost ratio |
| `direction` | `1.0` | Forward tracking (in the direction of groundwater flow) |
| `initial_dt` | `1.0` | Initial time step size (days) |
| `max_dt` | `100.0` | Maximum allowed time step (days) |
| `retardation_enabled` | `false` | No retardation — particles move at pore velocity |
| `adaptive` | (object) | Adaptive step-size control parameters |
| `dispersion` | `{"method": "None"}` | No dispersion — purely advective tracking |
| `capture` | (object) | Termination criteria for particle tracking |

### Adaptive Stepping Parameters

| Field | Value | Description |
|-------|-------|-------------|
| `tolerance` | `1e-6` | Local error tolerance for step acceptance |
| `safety` | `0.9` | Safety factor applied to predicted optimal step size |
| `alpha` | `0.2` | PI controller exponent for step-size scaling |
| `min_scale` | `0.2` | Minimum step-size scale factor (prevents drastic shrinkage) |
| `max_scale` | `5.0` | Maximum step-size scale factor (prevents drastic growth) |
| `max_rejects` | `10` | Maximum consecutive rejected steps before error |
| `min_dt` | `1e-10` | Absolute minimum time step (days) |
| `euler_dt` | `1.0` | Fixed step size used by the Euler solver |

### Capture (Termination) Parameters

| Field | Value | Description |
|-------|-------|-------------|
| `max_time` | `365250.0` | Maximum tracking time — 1000 years in days |
| `max_steps` | `1000000` | Maximum number of integration steps |
| `stagnation_velocity` | `1e-12` | Velocity below which a particle is considered stagnant |
| `stagnation_limit` | `100` | Consecutive stagnant steps before termination |

## What This Config Does

Uses the DormandPrince adaptive solver for forward advective particle tracking with no dispersion and no retardation. Particles are tracked for up to 1000 years or 1,000,000 steps, whichever comes first. Stagnant particles (velocity below 10⁻¹² m/day for 100 consecutive steps) are terminated early.

!!! info "Schema Validation"
    This configuration has been validated against [`mp3du_schema.json`](../reference/schema-reference.md).

## See Also

- [Complete Configuration](complete-config.md) — All options exercised
- [Building Configs](../guides/building-configs.md) — Interactive configuration guide
- [Schema Reference](../reference/schema-reference.md) — Full property contract
