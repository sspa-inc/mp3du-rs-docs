# Dispersion Theory

Mathematical foundations of stochastic particle tracking in mod-PATH3DU.

## Overview

In groundwater flow, **mechanical dispersion** causes solute particles to spread beyond what pure advection predicts. This spreading arises from velocity variations at scales smaller than the model grid. mod-PATH3DU models dispersion by adding stochastic perturbations to particle trajectories, transforming the deterministic advection ODE into a stochastic differential equation (SDE).

Two dispersion formulations are available:

- **GSDE** — The Generalized Stochastic Differential Equation method (LaBolle et al., 2000, eqs. 17a–17c)
- **Ito** — The Itô–Fokker–Planck formulation with explicit drift correction (Salamon et al., 2006)

Setting `"method": "None"` disables dispersion entirely, producing pure advective tracking.

## The Dispersion Tensor

Both methods rely on the **Burnett–Frind dispersion tensor** (Burnett and Frind, 1987) that relates dispersivity parameters to the local velocity field. In three dimensions, the hydrodynamic dispersion tensor is:

$$
D_{ij} = \alpha_T |\mathbf{V}| \delta_{ij} + (\alpha_L - \alpha_T) \frac{V_i V_j}{|\mathbf{V}|}
$$

where:

- $\alpha_L$ — longitudinal dispersivity (spreading along the flow direction)
- $\alpha_T$ — transverse dispersivity (spreading perpendicular to flow)
- $|\mathbf{V}|$ — magnitude of the velocity vector
- $\delta_{ij}$ — Kronecker delta
- $V_i, V_j$ — components of the velocity vector

!!! info "Three dispersivity parameters"
    mod-PATH3DU distinguishes **horizontal transverse** ($\alpha_{Th}$) and **vertical transverse** ($\alpha_{Tv}$) dispersivity, giving three parameters: `alpha_l`, `alpha_th`, and `alpha_tv`. The tensor then has the flow direction, a horizontal transverse direction and a vertical transverse direction as its principal axes; [Dispersion Methods](../reference/dispersion-methods.md#dispersion-tensor) gives its components. The three are given either per cell or once, for every cell, in the configuration; see [Giving the Dispersivities](../reference/dispersion-methods.md#giving-the-dispersivities).

The random step uses a matrix $\mathbf{B}$ with $\mathbf{B} \mathbf{B}^T = 2\mathbf{D}$, built from these principal axes.

## GSDE Formulation

### Governing Equation

A random walk reproduces the advection-dispersion equation only when a drift is added to the random step:

$$
d\mathbf{X} = \left[\mathbf{V}(\mathbf{X}, t) + \theta^{-1}\nabla \cdot (\theta\mathbf{D})\right] dt + \mathbf{B}(\mathbf{X}, t) \, d\mathbf{W}
$$

where:

| Symbol | Meaning |
|--------|---------|
| $\mathbf{X}$ | Particle position vector |
| $\mathbf{V}$ | Deterministic velocity at the particle location |
| $\theta$ | Porosity |
| $\mathbf{B}$ | Dispersion matrix satisfying $\mathbf{B}\mathbf{B}^T = 2\mathbf{D}$ |
| $d\mathbf{W}$ | Wiener process increment ($\sim \mathcal{N}(0, dt)$) |

Without the drift, particles collect where dispersion is low.

### Drift Without Gradients

The key advantage of the GSDE is that it **does not compute $\nabla \cdot \mathbf{D}$** — the divergence of the dispersion tensor. This term is difficult to compute numerically and is undefined at material interfaces (e.g., boundaries between geological units with different dispersivities).

The GSDE of LaBolle et al. (2000) instead evaluates the dispersion at trial points reached with the **same** random numbers as the step itself: a trial point $\mathbf{X} + \mathbf{S}(\mathbf{X})\Delta\mathbf{W}$, and one point along each principal direction of $\mathbf{D}$, where $\mathbf{S}$ is the symmetric square root of $2\mathbf{D}$. Combining the dispersion at these points, weighted by the ratio of porosities, gives a step whose mean is exactly the drift $\theta^{-1}\nabla \cdot (\theta\mathbf{D})\,\Delta t$, and whose spread is $2\mathbf{D}\,\Delta t$. mod-PATH3DU 2.1.9 (November 2026) and MP3DU-RS 0.1.5 implement their anisotropic form, eqs. 17a–17c; the equations are on the [Dispersion Methods](../reference/dispersion-methods.md#mathematical-formulation) page.

!!! warning "Changed in 0.1.5"
    Earlier versions drew the second step from independent random numbers, which removes the drift. Results with dispersion from earlier versions should be recomputed.

### Implementation Details

- Random numbers are generated using a **deterministic ChaCha8 RNG** seeded by particle ID, so a run repeated on the same computer gives the same trajectories; between platforms they can differ (see [Results on Different Platforms](../getting-started/install.md#results-on-different-platforms))
- Each particle receives an independent random stream, and one random vector drives all the trial points of a step
- The Wiener increment is drawn from $\mathcal{N}(0, \Delta t)$ per dimension
- Trial points are located by position, in the particle's layer or in the layer above or below, and take the dispersivities and porosity of the cell they lie in
- In backward tracking the dispersive displacement keeps its direction, while advection reverses

## Ito Formulation

### Governing Equation

The Itô formulation explicitly includes the drift correction term:

$$
d\mathbf{X} = \left(\mathbf{V} + \nabla \cdot \mathbf{D}\right) dt + \mathbf{B} \, d\mathbf{W}
$$

The additional drift correction $\nabla \cdot \mathbf{D}$ ensures that the particle density evolves according to the Fokker–Planck equation — the correct macroscopic transport equation. MP3DU-RS takes the porosity as uniform here; where it varies smoothly, the drift is $\theta^{-1}\nabla \cdot (\theta\mathbf{D})$, which the GSDE produces. At a jump in porosity between layers the GSDE does not produce it (see the known issue in [Layers and Boundaries](#layers-and-boundaries)).

### Drift Correction

The drift correction vector has components:

$$
(\nabla \cdot \mathbf{D})_i = \sum_j \frac{\partial D_{ij}}{\partial x_j}
$$

This term is required because Itô calculus does not automatically conserve the correct macroscopic concentration distribution. Without it, particles would artificially accumulate in regions of low dispersion.

### Numerical Computation of $\nabla \cdot \mathbf{D}$

mod-PATH3DU computes the divergence numerically using **central finite differences**:

$$
\frac{\partial D_{ij}}{\partial x_j} \approx \frac{D_{ij}(\mathbf{x} + h\mathbf{e}_j) - D_{ij}(\mathbf{x} - h\mathbf{e}_j)}{2h}
$$

This requires **6 additional velocity evaluations** per time step for the differences (2 per spatial dimension: $\pm h$ in $x$, $y$, and $z$), besides the evaluations at the particle, making the Ito method more computationally expensive than the GSDE. The differences straddle cell faces where the velocity can jump, which the GSDE avoids.

### Ito vs. Stratonovich

The Itô and Stratonovich interpretations of SDEs differ in how they handle the relationship between the stochastic integral and the drift term:

- **Itô:** The integrand is evaluated at the *beginning* of each interval. Requires an explicit drift correction to produce the correct Fokker–Planck equation.
- **Stratonovich:** The integrand is evaluated at the *midpoint*. The drift correction is implicit but requires different numerical treatment.

mod-PATH3DU uses the **Itô convention** because it pairs naturally with the explicit drift correction computation and is standard in the groundwater transport literature.

## Comparison

| Property | GSDE | Ito |
|----------|------|-----|
| Drift correction | From trial points ($\theta^{-1}\nabla \cdot (\theta\mathbf{D})$) | Explicit ($\nabla \cdot \mathbf{D}$) |
| Spatial gradient of $\mathbf{D}$ required | No | Yes |
| Extra velocity evaluations per step | Up to 5 | 8 |
| Material interface handling | Robust | Requires care |
| Computational cost | Lower | Higher |
| Accuracy | High | High |

!!! tip "Which method should I use?"
    Start with **GSDE** for most applications. It is more robust at material interfaces and computationally cheaper, and it takes dispersivities that differ between cells, which Itô refuses. Use **Ito** when you need exact Fokker–Planck consistency or are validating against analytical solutions that assume the Itô convention.

## Step Size

With dispersion, results depend on the step size as well as on the number of particles. The random-walk part of each step is computed from the start of the step, so it is accurate only to first order in the step size, and the solver's `tolerance` controls only the advective part. Away from wells the step is usually set by `max_dt`; near them, by the advective error test.

Where wells capture particles, the dependence was large and slow to vanish up to 0.1.6, which took the advection of a step from where the step started. Since 0.1.7 the dispersive displacement comes first and the advection follows from where the particle lands (see [Layers and Boundaries](#layers-and-boundaries)), and in the MEUK example the dependence is small. Example 5a, 144,000 particles, `DormandPrince`, fraction of particles captured by 23,363 days:

| `max_dt` | 0.1.7 | Order of 0.1.6, with the first-stage fix of 0.1.7 |
|---|---|---|
| 1,000 days | 6.0% | 4.7% |
| 250 days | 5.8% | 5.3% |
| 62.5 days | 5.8% | 5.7%, still rising |

MT3D gives 5.6%. mod-PATH3DU 2.1.9, with its own settings (step-doubling Runge-Kutta, no step limit), gives 5.0%, as MP3DU-RS 0.1.6 did; MP3DU-RS 0.1.7 gives 6.0% with those settings. Released 0.1.6 gave 5.2% with `DormandPrince` and a 1,000-day `max_dt`.

A dispersive displacement is not checked for capture in the cells it passes through, only the advective steps after it where each ends. With long steps a particle can therefore cross a well's capture zone uncounted.

So:

- **To check a result,** rerun it with `max_dt` reduced by a factor of four. Repeat until it stops changing within the Monte Carlo error.
- **When comparing with another code,** or with an earlier run, use the same solver, `tolerance` and `max_dt`. Otherwise differences in the step sizes can look like differences in the method.

A test of the boundaries: a column of length $L = 10$ with uniform upward flow at $v = 1$, initially full of solute, compared with a finite-difference solution with Danckwerts conditions (no total flux through the face where clean water enters, no dispersive flux through the face where it leaves), at Peclet numbers $vL/D$ of 10 and 1 ($\alpha_L$ = 1 and 10). The transit time is $L/v$ = 10 days. With steps of a twentieth of the transit time, the solute left after one transit time is 1.4% too low at a Peclet number of 10 and 0.4% too low at 1, and the difference vanishes as the step shrinks. In this uniform flow the result does not depend on how the column is divided into layers. With very long steps it is far off: 22% too little solute at a Peclet number of 1 with `max_dt` 1000 in a review run.

## Layers and Boundaries

Since 0.1.7 a step with dispersion has two parts (a step here is the interval between two dispersive displacements; the advective motion within it can take several solver steps):

- **The dispersive displacement comes first,** computed where the particle is. It is not cut at the first face it crosses, because that would shrink its random part: its vertical part is followed through every cell it reaches, measured in each cell's saturated thickness. At a face with no wet cell beyond (the top or bottom of the model, a dry cell, or the water table) it is reflected, as a random walk must be at a boundary through which no solute disperses.
- **The particle then moves by advection from where it lands,** for the length of the step, as a particle without dispersion would (see [Steps That Reach a Top or Bottom Face](adaptive-stepping.md#steps-that-reach-a-top-or-bottom-face)). It leaves through a face with no wet cell beyond only where the flow carries it out, as with the usual zero-gradient (Danckwerts) outflow condition. A boundary on that face can capture it; otherwise it ends `ExitedDomain`.

The next displacement comes when the step's full length has passed, however the advective motion was divided at faces, and the length of the next step follows the solver's error control as if there were no faces. Where the flow is uniform, the result therefore does not depend on how the model is divided into layers. Where the velocity varies within the cells and the steps may grow (`initial_dt` below `max_dt`), the steps in thin layers, where most advective steps are cut at a face, stay near `initial_dt`, while in a thick layer they follow the solver's error control. Keep `initial_dt` no larger than a step you would accept for the dispersion. A particle that reaches a face where the vertical flow converges from both sides ends there `Stagnated`, with or without dispersion.

Before 0.1.7, a step that spanned more than one layer stopped on the next layer's far face, which reduced the vertical spread in thin layers. A particle dispersed through a no-flow top or bottom was lost.

!!! warning "Known issue: an empty strip next to an inflow face"
    Where water enters through a face with no wet cell beyond, such as the bottom of a model with upward flow or a water table with recharge, the dispersive part of a step is reflected at the face and the advective part then moves the particle away from it. No particle therefore ends a step closer to the face than that step's advective displacement. In the test column above, with steps of a twentieth of the transit time, that strip was empty where the exact solution holds 3.6% of the solute then in the column (Peclet number 1). The strip narrows as the step shrinks.

!!! warning "Known issue: the GSDE next to a face where the dispersion changes with depth"
    A trial point of the GSDE beyond a top or bottom face with no wet cell beyond is evaluated at the face. Where the dispersion coefficient changes with depth, an evenly mixed solute then does not stay evenly mixed next to the face: in a test with the vertical dispersion doubling from bottom to top, the density in the bottom tenth of the column was 5% too high with steps of 1 and 12% with steps of 5. In the column test with the velocity rising by 10% per unit height and a Peclet number of 1, the solute left after one transit time was 31% too high with steps of 0.5 and 13% with steps of 0.1. The Itô method keeps an evenly mixed solute evenly mixed (within 1%), and was within 3.5% in that column test.

!!! warning "Known issue: jumps in porosity"
    At a jump in porosity between layers, the GSDE does not keep an evenly mixed solute evenly mixed: layers of lower porosity collect too many particles. In a test across one interface, with porosity four times higher below, 77.8% of the particles ended below, against an exact 80%, whatever the step size. Jumps in dispersivity or velocity alone are handled. This has been so since 0.1.5 and is not yet fixed.

## Configuration

Dispersion is configured in the `SimulationConfig` JSON. The dispersivities are given there, as below, for every cell, or per cell to `hydrate_cell_properties()` or `hydrate_sspa_inputs()` with only `"method"` in the JSON: one or the other, never both (see [Giving the Dispersivities](../reference/dispersion-methods.md#giving-the-dispersivities)).

=== "GSDE"

    ```json
    "dispersion": {
        "method": "Gsde",
        "alpha_l": 10.0,
        "alpha_th": 1.0,
        "alpha_tv": 0.1
    }
    ```

=== "Ito"

    ```json
    "dispersion": {
        "method": "Ito",
        "alpha_l": 10.0,
        "alpha_th": 1.0,
        "alpha_tv": 0.1
    }
    ```

=== "None"

    ```json
    "dispersion": {
        "method": "None"
    }
    ```

See [Dispersion Methods](../reference/dispersion-methods.md) for the complete parameter specification.

## Mathematical Background

The dispersion methods in mod-PATH3DU are based on the following references:

- **LaBolle, E.M., Fogg, G.E., and Tompson, A.F.B.** (1996). Random-walk simulation of transport in heterogeneous porous media: Local mass-conservation problem and implementation methods. *Water Resources Research*, 32(3), 583–593.
- **LaBolle, E.M., Quastel, J., Fogg, G.E., and Gravner, J.** (2000). Diffusion processes in composite porous media and their numerical integration by random walks: Generalized stochastic differential equations with discontinuous coefficients. *Water Resources Research*, 36(3), 651–662.
- **Salamon, P., Fernàndez-Garcia, D., and Gómez-Hernández, J.J.** (2006). A review and numerical assessment of the random walk particle tracking method. *Journal of Contaminant Hydrology*, 87(3-4), 277–305.
- **Burnett, R.D. and Frind, E.O.** (1987). Simulation of contaminant transport in three dimensions: 2. Dimensionality effects. *Water Resources Research*, 23(4), 695–705.
