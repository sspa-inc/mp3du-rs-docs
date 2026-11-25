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

The error is measured relative to the size of the model. Each component of the estimated position error is divided by the model extent in that direction ($x_{\max} - x_{\min}$, $y_{\max} - y_{\min}$, $z_{\max} - z_{\min}$) before it is compared with the tolerance. A tolerance of $10^{-6}$ therefore allows a position error of about one millionth of the model extent per step, wherever the grid's origin is.

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
| $\alpha$ | Scaling exponent | 0.2 (for a 4th/5th-order pair) |
| $\text{tol}$ | User-specified tolerance | $10^{-6}$ |
| $\text{err}$ | Estimated error from the embedded pair | — |

The scaling exponent $\alpha$ is derived from the order of the error estimate. For a pair of orders $p$ and $p+1$, the usual exponent is $\alpha = 1/(p+1)$: 0.2 for the 4th/5th-order pairs (DormandPrince, CashKarp) and for Rk4StepDoubling, whose step-doubling estimate is the error of its 4th-order step, and 1/6 (about 0.167) for the 5th/6th-order Verner pairs.

## Safety Factor

The safety factor $S < 1$ makes step size adjustments **conservative**. Without it, the step would be sized exactly to meet the tolerance — and random fluctuations would cause frequent rejections on the next step. A safety factor of 0.9 means the new step is sized to use 90% of the theoretical maximum, leaving a margin for error variability.

## Scale Limits

The step size scaling is clamped to prevent extreme changes:

- `min_scale` — the smallest allowed scaling factor (e.g., 0.2 means the step can shrink to at most 1/5th)
- `max_scale` — the largest allowed scaling factor (e.g., 5.0 means the step can grow to at most 5×). The embedded solvers (`DormandPrince`, `CashKarp` and the Verner solvers) also never grow a step more than fourfold, as mod-PATH3DU's Dormand-Prince does; `Rk4StepDoubling` grows it by up to `max_scale`.

These limits prevent pathological behaviour where a single unusual step causes the algorithm to overshoot or collapse the step size.

## Minimum and Maximum Step Constraints

Users can set absolute bounds on the step size via the `adaptive` configuration:

| Field | Description |
|-------|-------------|
| `min_dt` | Smallest allowed time step. If the algorithm needs a step smaller than this, it signals an error. |
| `euler_dt` | Threshold for the adaptive solvers' emergency Euler step. If the step shrinks to `euler_dt` or below, the solver takes a forward-Euler step of `euler_dt`, with no error control. Set it equal to `min_dt` (`1e-10` in these examples): a larger value puts a floor under the step size and degrades accuracy near wells, and a smaller one disables the fallback, so a step that cannot meet the tolerance ends the pathline as `SolverFailed`. The `Euler` solver does not use it. |

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
| `Euler` | No | Fixed step (`initial_dt`, capped at `max_dt`) |
| `Rk4StepDoubling` | Yes | Step doubling (compares full and half steps) |
| `DormandPrince` | Yes | Embedded pair (4th/5th order) |
| `CashKarp` | Yes | Embedded pair (4th/5th order) |
| `VernerRobust` | Yes | Embedded pair (5th/6th order) |
| `VernerEfficient` | Yes | Embedded pair (5th/6th order) |

See [Solver Methods](../reference/solver-methods.md) for full mathematical details and Butcher tableaux for each solver.

!!! tip
    Start with **DormandPrince** and the default tolerance ($10^{-6}$). Tighten the tolerance only if you need higher accuracy and can afford the computational cost. Switch to **VernerRobust** or **VernerEfficient** for problems requiring very high accuracy; for the Waterloo field, see the note on VernerEfficient in [Solver Methods](../reference/solver-methods.md#vernerefficient).

## Stage Coordinate Handling in Layered Models

During multi-stage RK evaluation, intermediate stage points can temporarily drift outside the current cell's vertical range — the local $z$ coordinate drops below 0 or rises above 1. This is normal and expected for large steps in regions with steep vertical velocity gradients.

mod-PATH3DU **clamps** these out-of-range stage $z$ values to $[0, 1]$ before evaluating the velocity. This prevents the Pollock linear interpolation from extrapolating beyond the cell, which would produce artificially large vertical velocities and bias the trajectory.

This behavior is critical for multi-layer models. Without clamping, all higher-order solvers (RK4, Dormand-Prince, Cash-Karp, Verner) produce trajectories that plunge too deep at layer boundaries, while Euler — which only evaluates at accepted positions — remains unaffected.

!!! note "Implementation detail"
    The clamp is applied inside `velocity_at_stage()` in `mp3du-velocity/src/field.rs`, which is the common path for all stage evaluations across all solvers. The accepted particle position is handled separately by the orchestrator's layer-transition logic.

### Steps That Reach a Top or Bottom Face

Because every stage stays in the starting cell's layer, a step that crossed into the next layer would move at the old layer's velocity to its end. The error estimate cannot see that. Since 0.1.7 the following rules apply; the rejection, the cut and the restart follow mod-PATH3DU 2.1.9 (which shrinks a rejected step by about 12% at a time, where MP3DU-RS aims the retry 0.5% past the face), and the others are MP3DU-RS's own:

- **Rejection:** a trial step that would end more than 1% of the cell's saturated thickness beyond its top or bottom face is rejected. The retry is aimed 0.5% past the face, and these rejections do not count against `max_rejects`.
- **Cut:** an accepted step that ends beyond the face is cut there.
  - The particle stops on the face, and the time advances by the part of the step that took it there.
  - It is recorded, and checked for capture, in the cell it is leaving.
  - Then it continues in the cell beyond, where its next step starts again from `initial_dt`. A boundary there that captures particles as they enter (IFACE 0 without a capture radius, 2 or 7) therefore stops the particle within one initial step of the face.
- **No wet cell beyond:** the particle stays on the face. An IFACE 5 or 6 boundary there can capture it; otherwise it ends `ExitedDomain`, with the reason "No wet cell beyond the top face" (or bottom face).
- **Converging flow:** where the vertical flow converges on the face from both sides, the particle cannot leave it, and ends `Stagnated`, with the reason "Stuck on a layer face".

With dispersion these rules apply to the advective motion only. The dispersive displacement, made at the start of each step, is not cut, because that would shrink its random part. See [Layers and Boundaries](dispersion-theory.md#layers-and-boundaries) in Dispersion Theory.
