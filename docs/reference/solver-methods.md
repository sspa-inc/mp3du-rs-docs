# Solver Methods

mod-PATH3DU provides six Runge-Kutta ODE integration solvers for computing particle trajectories through velocity fields. These range from a first-order Euler fallback to high-order embedded pairs with adaptive step-size control.

## Solver Comparison Table

| Solver | Order | Stages | Embedded | Adaptive | FSAL | Recommended Use Case |
|--------|-------|--------|----------|----------|------|---------------------|
| Euler | 1 | 1 | No | No | No | Emergency fallback for stiff/near-singular cells |
| Rk4StepDoubling | 4 | 4×3 | No | Yes (Richardson) | No | General purpose, moderate accuracy |
| DormandPrince | 5(4) | 7 | Yes | Yes | Yes | Default choice — best accuracy/cost ratio |
| CashKarp | 5(4) | 6 | Yes | Yes | No | Alternative to Dormand-Prince |
| VernerRobust | 6(5) | 9 | Yes | Yes | Yes | High accuracy, robust error estimation |
| VernerEfficient | 6(5) | 9 | Yes | Yes | Yes | Highest accuracy, smooth velocity fields |

!!! info "Schema Values"
    Solver names in the JSON Schema are exact string values: `"Euler"`, `"Rk4StepDoubling"`, `"DormandPrince"`, `"CashKarp"`, `"VernerRobust"`, `"VernerEfficient"`.

---

## Euler

Forward Euler — a first-order, single-stage integrator. One velocity evaluation per step. No error estimation or adaptive step-size control.

Used as an emergency fallback when the adaptive embedded solvers shrink the step size below the `euler_dt` threshold (typically $10^{-20}$). Not recommended for production simulations.

### Mathematical Formulation

$$\mathbf{k}_1 = \mathbf{f}(t_n, \mathbf{y}_n)$$

$$\mathbf{y}_{n+1} = \mathbf{y}_n + h \, \mathbf{k}_1$$

where $\mathbf{f}$ is the velocity field evaluation and $h$ is the step size.

- **Order:** 1
- **Stages:** 1
- **Velocity evaluations per step:** 1
- **Adaptive:** No — $\Delta t_\text{next} = \Delta t$

---

## Rk4StepDoubling

Classic fourth-order Runge-Kutta with Richardson step-doubling for adaptive error control. Computes one full RK4 step and two half-steps, then uses the difference for error estimation.

### Mathematical Formulation

The standard RK4 stages:

$$\mathbf{k}_1 = \mathbf{f}(t_n, \mathbf{y}_n)$$

$$\mathbf{k}_2 = \mathbf{f}\!\left(t_n + \tfrac{h}{2},\; \mathbf{y}_n + \tfrac{h}{2}\,\mathbf{k}_1\right)$$

$$\mathbf{k}_3 = \mathbf{f}\!\left(t_n + \tfrac{h}{2},\; \mathbf{y}_n + \tfrac{h}{2}\,\mathbf{k}_2\right)$$

$$\mathbf{k}_4 = \mathbf{f}(t_n + h,\; \mathbf{y}_n + h\,\mathbf{k}_3)$$

$$\mathbf{y}_{n+1} = \mathbf{y}_n + \frac{h}{6}\left(\mathbf{k}_1 + 2\mathbf{k}_2 + 2\mathbf{k}_3 + \mathbf{k}_4\right)$$

### Step-Doubling Error Control

1. Compute $\mathbf{y}_\text{full}$ with one RK4 step of size $h$.
2. Compute $\mathbf{y}_\text{double}$ with two RK4 steps of size $h/2$.
3. Error estimate: $\varepsilon = |\mathbf{y}_\text{full} - \mathbf{y}_\text{double}|$.
4. Accepted solution uses Richardson extrapolation:

$$\mathbf{y}_\text{accepted} = \mathbf{y}_\text{double} + \frac{\mathbf{y}_\text{double} - \mathbf{y}_\text{full}}{15}$$

5. Step-size adjustment: $h_\text{new} = S \cdot h \cdot (\varepsilon / \text{tol})^{-\alpha}$, clamped to $[\text{min\_scale} \cdot h,\; \text{max\_scale} \cdot h]$.

- **Order:** 4
- **Stages:** 4 per RK4 call × 3 calls (full + 2 half) = 12 velocity evaluations per accepted step
- **Adaptive:** Yes (Richardson step-doubling)

---

## DormandPrince

Dormand-Prince 5(4) embedded Runge-Kutta method (DOPRI). Uses 7 stages with a built-in error estimator from the difference between the 5th-order and 4th-order solutions. Supports FSAL (First Same As Last), reusing the last stage velocity as the first stage of the next step.

### Butcher Tableau

$$\begin{array}{c|ccccccc}
0 \\
1/5 & 1/5 \\
3/10 & 3/40 & 9/40 \\
4/5 & 44/45 & -56/15 & 32/9 \\
8/9 & 19372/6561 & -25360/2187 & 64448/6561 & -212/729 \\
1 & 9017/3168 & -355/33 & 46732/5247 & 49/176 & -5103/18656 \\
1 & 35/384 & 0 & 500/1113 & 125/192 & -2187/6784 & 11/84 \\
\hline
b_i & 35/384 & 0 & 500/1113 & 125/192 & -2187/6784 & 11/84 & 0 \\
\hat{b}_i & 5179/57600 & 0 & 7571/16695 & 393/640 & -92097/339200 & 187/2100 & 1/40 \\
\end{array}$$

- **Order:** 5 (with 4th-order embedded error estimate)
- **Stages:** 7
- **Effective evaluations per step:** 6 (due to FSAL)
- **Adaptive:** Yes (embedded error estimate)

!!! tip
    For most simulations, `DormandPrince` provides the best balance of accuracy and performance. It is the recommended default solver.

---

## CashKarp

Cash-Karp 5(4) embedded Runge-Kutta method. Uses 6 stages. Does not support FSAL.

### Butcher Tableau

$$\begin{array}{c|cccccc}
0 \\
1/5 & 1/5 \\
3/10 & 3/40 & 9/40 \\
3/5 & 3/10 & -9/10 & 6/5 \\
1 & -11/54 & 5/2 & -70/27 & 35/27 \\
7/8 & 1631/55296 & 175/512 & 575/13824 & 44275/110592 & 253/4096 \\
\hline
b_i & 37/378 & 0 & 250/621 & 125/594 & 0 & 512/1771 \\
\hat{b}_i & 2825/27648 & 0 & 18575/48384 & 13525/55296 & 277/14336 & 1/4 \\
\end{array}$$

- **Order:** 5 (with 4th-order embedded error estimate)
- **Stages:** 6
- **Adaptive:** Yes (embedded error estimate)

---

## VernerRobust

Verner Robust 9(6)5 embedded method. A 9-stage method with a 6th-order solution and 5th-order error estimate. Robust error estimation across a wide range of problem types. Supports FSAL.

### Butcher Tableau

The Verner Robust method uses 9 stages with the following node fractions $c_i$:

$$c = \left[0,\; \frac{9}{50},\; \frac{1}{6},\; \frac{1}{4},\; \frac{53}{100},\; \frac{3}{5},\; \frac{4}{5},\; 1,\; 1\right]$$

High-order weights $b_i$:

$$b = \left[\frac{11}{144},\; 0,\; 0,\; \frac{256}{693},\; 0,\; \frac{125}{504},\; \frac{125}{528},\; \frac{5}{72},\; 0\right]$$

!!! note
    The complete stage coefficient matrix is available in the source code at `mp3du-rs/crates/mp3du-solver/src/tableaux.rs`. The full tableau is too large to reproduce here.

- **Order:** 6 (with 5th-order embedded error estimate)
- **Stages:** 9
- **Effective evaluations per step:** 8 (due to FSAL)
- **Adaptive:** Yes (embedded error estimate)

---

## VernerEfficient

Verner Efficient 9(6)5 embedded method. Optimized for computational efficiency compared to Verner Robust while maintaining 6th-order accuracy. Uses rational coefficients with large numerators/denominators for maximum numerical precision. Supports FSAL.

### Butcher Tableau

Node fractions $c_i$:

$$c = \left[0,\; \frac{3}{50},\; \frac{1439}{15000},\; \frac{1439}{10000},\; \frac{4973}{10000},\; \frac{389}{400},\; \frac{1999}{2000},\; 1,\; 1\right]$$

!!! note
    The complete stage coefficient matrix is available in the source code at `mp3du-rs/crates/mp3du-solver/src/tableaux.rs`. Verner Efficient uses very large rational coefficients optimized for extended precision.

- **Order:** 6 (with 5th-order embedded error estimate)
- **Stages:** 9
- **Effective evaluations per step:** 8 (due to FSAL)
- **Adaptive:** Yes (embedded error estimate)

---

## Adaptive Step-Size Control

All solvers except Euler use adaptive step-size control. The adaptive parameters are configured via the `adaptive` section of the JSON Schema.

The general step-size update formula for embedded methods is:

$$h_\text{new} = S \cdot h \cdot \left(\frac{\varepsilon}{\text{tol}}\right)^{-\alpha}$$

where:

- $S$ = `safety` factor (typically 0.9)
- $\varepsilon$ = maximum relative error across all components
- $\text{tol}$ = `tolerance`
- $\alpha$ = step-size exponent

The resulting scale factor is clamped to $[\text{min\_scale},\; \text{max\_scale}]$ to prevent extreme step-size changes.

| Parameter | Schema Field | Description |
|-----------|-------------|-------------|
| Tolerance | `adaptive.tolerance` | Target relative error per step |
| Safety factor | `adaptive.safety` | Conservative multiplier for step growth (< 1) |
| Exponent | `adaptive.alpha` | Controls step-size response to error |
| Min scale | `adaptive.min_scale` | Floor on $h_\text{new}/h$ ratio |
| Max scale | `adaptive.max_scale` | Ceiling on $h_\text{new}/h$ ratio |
| Max rejects | `adaptive.max_rejects` | Maximum step rejections before failure |
| Min dt | `adaptive.min_dt` | Below this, return `StepTooSmall` error |
| Euler dt | `adaptive.euler_dt` | Below this, fall back to Euler for one step |

!!! warning "Euler Fallback"
    When the adaptive step size shrinks below `euler_dt`, the embedded solver automatically falls back to a single Euler step to avoid infinite rejection loops near singularities.

For a detailed treatment of adaptive step-size control theory, see [Adaptive Stepping](../concepts/adaptive-stepping.md).

---

## Stage Z-Coordinate Clamping

All adaptive solvers (RK4 step-doubling and embedded methods) evaluate the velocity field at **intermediate stage points** during each step. In layered models, these stage points can temporarily overshoot the current cell's vertical extent, producing a local $z$ coordinate outside $[0, 1]$.

The Waterloo velocity evaluator computes vertical velocity using the Pollock linear interpolation:

$$v_z = \frac{(1-z)\,v_\text{bot} + z\,v_\text{top}}{\Delta z_\text{sat}}$$

If $z$ is allowed to extrapolate beyond $[0, 1]$, this formula produces **exaggerated vertical velocities** that bias the trajectory. In multi-layer models, this causes all higher-order solvers to diverge while Euler (which only evaluates at accepted particle positions, always in $[0, 1]$) remains unaffected.

To prevent this, `velocity_at_stage()` **clamps the z-coordinate to $[0, 1]$** before evaluating the velocity. This matches the C++ behavior, where both `step_doubling::calc_step` and `embedded_method::calc_step` clamp stage $z$ to cell faces at every intermediate evaluation:

```cpp
// C++ stage z-clamping (cls_tracker.cpp)
if (sample_z < 0.) { sample_z = 0.; }
else if (sample_z > 1.) { sample_z = 1.; }
```

!!! info "Why only stages?"
    The clamp applies only to **intermediate stage evaluations** during multi-stage RK methods. The accepted particle position after each step is handled by the orchestrator's layer-transition logic, which properly relocates the particle into the correct adjacent cell.
