# Adaptive Stepping

How mod-PATH3DU dynamically controls integration step size for accuracy and efficiency.

## Why Adaptive Steps?

Particle tracking through a heterogeneous velocity field encounters regions of vastly different complexity. Near wells, geological boundaries, or sharp velocity gradients, small time steps are needed to maintain accuracy. In smooth, uniform regions, large steps suffice.

**Fixed-step integration** forces a trade-off: a step small enough for the hardest regions wastes computation everywhere else, while a step large enough for efficiency loses accuracy where it matters most.

**Adaptive stepping** resolves this by automatically adjusting $\Delta t$ at every step based on a local error estimate. Steps are large where the velocity is smooth and small where it varies rapidly.

## Error Estimation

mod-PATH3DU uses **embedded Runge–Kutta pairs** to estimate the local truncation error without extra function evaluations. An embedded pair consists of two methods of different order — say order $p$ and order $p+1$ — that share the same intermediate stage evaluations.

The error estimate is the difference between the two solutions:

$$
\mathbf{e}_{n+1} = \mathbf{y}_{n+1}^{(p+1)} - \mathbf{y}_{n+1}^{(p)}
$$

The scalar error norm is computed as:

$$
\text{err} = \left\| \mathbf{e}_{n+1} \right\|
$$

This measures how much the two solutions disagree. A small error means the lower-order solution is already accurate, and the step can be accepted (or even enlarged).

!!! info "Step-doubling exception"
    The `Rk4StepDoubling` solver uses a different strategy: it takes one full step and two half-steps of the same method, comparing the results. This is less efficient than embedded pairs but applies to any RK method.

## Step Acceptance Criterion

A step is **accepted** when the error estimate is within the user-specified tolerance:

$$
\text{err} \leq \text{tol}
$$

When the error exceeds the tolerance, the step is **rejected**: the result is discarded, the step size is reduced, and the step is retried.

## Step Size Scaling

After each step (accepted or rejected), a new step size is computed:

$$
h_{\text{new}} = h \cdot S \cdot \left(\frac{\text{tol}}{\text{err}}\right)^{\alpha}
$$

where:

| Parameter | Description | Typical value |
|-----------|-------------|---------------|
| $h$ | Current step size | — |
| $S$ | Safety factor | 0.9 |
| $\alpha$ | Scaling exponent | 0.2 (for a 5th-order pair) |
| $\text{tol}$ | User-specified tolerance | $10^{-6}$ |
| $\text{err}$ | Estimated error from the embedded pair | — |

The scaling exponent $\alpha$ is derived from the order of the embedded pair. For a method of order $p$, the optimal exponent is $\alpha = 1/(p+1)$.

## Safety Factor

The safety factor $S < 1$ makes step size adjustments **conservative**. Without it, the step would be sized exactly to meet the tolerance — and random fluctuations would cause frequent rejections on the next step. A safety factor of 0.9 means the new step is sized to use 90% of the theoretical maximum, leaving a margin for error variability.

## Scale Limits

The step size scaling is clamped to prevent extreme changes:

- `min_scale` — the smallest allowed scaling factor (e.g., 0.2 means the step can shrink to at most 1/5th)
- `max_scale` — the largest allowed scaling factor (e.g., 5.0 means the step can grow to at most 5×)

These limits prevent pathological behaviour where a single unusual step causes the algorithm to overshoot or collapse the step size.

## Minimum and Maximum Step Constraints

Users can set absolute bounds on the step size via the `adaptive` configuration:

| Field | Description |
|-------|-------------|
| `min_dt` | Smallest allowed time step. If the algorithm needs a step smaller than this, it signals an error. |
| `euler_dt` | Fixed step size for the Euler solver (which is non-adaptive). |

The top-level `initial_dt` and `max_dt` fields control the starting step size and upper bound:

| Field | Description |
|-------|-------------|
| `initial_dt` | Time step for the first integration step |
| `max_dt` | Maximum allowed time step |

!!! warning
    Setting `min_dt` too small can cause the simulation to stall in difficult regions. Setting it too large can cause step rejections that trigger the `max_rejects` limit.

## Which Solvers Support Adaptive Stepping?

| Solver | Adaptive | Method |
|--------|----------|--------|
| `Euler` | No | Fixed step (`euler_dt`) |
| `Rk4StepDoubling` | Yes | Step doubling (compares full and half steps) |
| `DormandPrince` | Yes | Embedded pair (4th/5th order) |
| `CashKarp` | Yes | Embedded pair (4th/5th order) |
| `VernerRobust` | Yes | Embedded pair (6th/7th order) |
| `VernerEfficient` | Yes | Embedded pair (6th/7th order) |

See [Solver Methods](../reference/solver-methods.md) for full mathematical details and Butcher tableaux for each solver.

!!! tip
    Start with **DormandPrince** and the default tolerance ($10^{-6}$). Tighten the tolerance only if you need higher accuracy and can afford the computational cost. Switch to **VernerRobust** or **VernerEfficient** for problems requiring very high accuracy.

## Stage Coordinate Handling in Layered Models

During multi-stage RK evaluation, intermediate stage points can temporarily drift outside the current cell's vertical range — the local $z$ coordinate drops below 0 or rises above 1. This is normal and expected for large steps in regions with steep vertical velocity gradients.

mod-PATH3DU **clamps** these out-of-range stage $z$ values to $[0, 1]$ before evaluating the velocity. This prevents the Pollock linear interpolation from extrapolating beyond the cell, which would produce artificially large vertical velocities and bias the trajectory.

This behavior is critical for multi-layer models. Without clamping, all higher-order solvers (RK4, Dormand-Prince, Cash-Karp, Verner) produce trajectories that plunge too deep at layer boundaries, while Euler — which only evaluates at accepted positions — remains unaffected.

!!! note "Implementation detail"
    The clamp is applied inside `velocity_at_stage()` in `mp3du-velocity/src/field.rs`, which is the common path for all stage evaluations across all solvers. The accepted particle position is handled separately by the orchestrator's layer-transition logic.
