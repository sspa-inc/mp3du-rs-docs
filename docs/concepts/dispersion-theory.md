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

The additional drift correction $\nabla \cdot \mathbf{D}$ ensures that the particle density evolves according to the Fokker–Planck equation — the correct macroscopic transport equation. MP3DU-RS takes the porosity as uniform here; where it varies, the drift is $\theta^{-1}\nabla \cdot (\theta\mathbf{D})$, which the GSDE produces.

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
