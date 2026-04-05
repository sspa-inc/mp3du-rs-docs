# Invalid Configuration Examples

Common configuration mistakes and their validation errors.

!!! info
    These examples intentionally fail schema validation to demonstrate error messages and constraint enforcement.

## Invalid Solver Name

```json
--8<-- "docs/examples/configs/invalid-bad-solver.json"
```

!!! danger "Validation Error"
    `'RungeKutta4' is not one of ['Euler', 'Rk4StepDoubling', 'DormandPrince', 'CashKarp', 'VernerRobust', 'VernerEfficient']`

**Fix:** Use one of the exact solver names listed in the error message.

---

## Invalid Direction Value

```json
--8<-- "docs/examples/configs/invalid-bad-direction.json"
```

!!! danger "Validation Error"
    `0.5 is not one of [1.0, -1.0]`

**Fix:** Use `1.0` for forward tracking or `-1.0` for backward tracking.

---

## Missing Required Field

```json
--8<-- "docs/examples/configs/invalid-missing-required.json"
```

!!! danger "Validation Error"
    `'solver' is a required property`

**Fix:** Add the `"solver"` field with a valid solver name. All required fields are: `velocity_method`, `solver`, `adaptive`, `dispersion`, `retardation_enabled`, `capture`, `initial_dt`, `max_dt`, `direction`.

---

## Negative Dispersivity

```json
--8<-- "docs/examples/configs/invalid-negative-dispersivity.json"
```

!!! danger "Validation Error"
    `{'method': 'Gsde', 'alpha_l': -5.0, 'alpha_th': 1.0, 'alpha_tv': 0.1} is not valid under any of the given schemas`

**Fix:** Dispersivity values (`alpha_l`, `alpha_th`, `alpha_tv`) must be zero or positive. Change `alpha_l` from `-5.0` to a non-negative value.

---

## Wrong Type

```json
--8<-- "docs/examples/configs/invalid-wrong-type.json"
```

!!! danger "Validation Error"
    `42 is not of type 'string'`

**Fix:** The `solver` field must be a string, not a number. Use `"DormandPrince"` instead of `42`.

## See Also

- [Minimal Configuration](minimal-config.md) — The simplest valid config
- [Schema Reference](../reference/schema-reference.md) — Full constraints
- [Error Diagnostics](../reference/error-diagnostics.md) — Runtime error catalog
