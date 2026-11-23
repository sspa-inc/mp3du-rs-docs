# Dispersion Methods

mod-PATH3DU supports three dispersion modes for stochastic particle tracking. When dispersion is enabled, random perturbations are added to particle velocities to simulate mechanical dispersion in porous media.

## Dispersion Mode Comparison

| Mode | Stochastic | Parameters Required | Velocity Evaluations | Use Case |
|------|-----------|--------------------|-----------------------|----------|
| None | No | — | 0 extra | Advection-only tracking |
| Gsde | Yes | `alpha_l`, `alpha_th`, `alpha_tv` | Up to 5 extra (the particle and the trial points) | Standard dispersive transport — robust at material interfaces |
| Ito | Yes | `alpha_l`, `alpha_th`, `alpha_tv` | 8 extra (the particle and the numerical $\nabla \cdot \mathbf{D}$) | Itô SDE with explicit drift correction, for smooth fields |

!!! info "Schema Values"
    Dispersion method values in the JSON Schema: `"None"`, `"Gsde"`, `"Ito"`.

---

## None

No dispersion. Particles follow advective pathlines only. No random perturbation is applied.

```json
{
  "dispersion": {
    "method": "None"
  }
}
```

---

## Gsde

Generalized stochastic differential equation (GSDE) of LaBolle et al. (2000), in the anisotropic form of their eqs. 17a–17c, as mod-PATH3DU 2.1.9 has used since November 2026. This is the recommended dispersion method for most simulations.

!!! warning "Changed in 0.1.5"
    Before 0.1.5 the GSDE drew its second step from random numbers independent of the first, which removes the drift term, so particles collected where dispersion is low; its two-step form (eq. 11a) is also not exact for anisotropic dispersion. Backward tracking reversed the drift, and vertical dispersion was scaled by the cell thickness. Results with dispersion from earlier versions should be recomputed. See the [changelog](https://github.com/sspa-inc/mp3du-rs/blob/main/CHANGELOG.md).

### Parameters

| Parameter | Schema Field | Type | Constraints | Description |
|-----------|-------------|------|-------------|-------------|
| Longitudinal dispersivity | `alpha_l` | number | ≥ 0 | Dispersivity parallel to flow direction [L] |
| Transverse horizontal dispersivity | `alpha_th` | number | ≥ 0 | Dispersivity perpendicular to flow in the horizontal plane [L] |
| Transverse vertical dispersivity | `alpha_tv` | number | ≥ 0 | Dispersivity perpendicular to flow in the vertical plane [L] |

The dispersivities are uniform: they come from the configuration, and the per-cell values given to `hydrate_cell_properties()` are not used.

### Mathematical Formulation

A random walk reproduces the advection-dispersion equation only when a drift is added to the random step. The Itô SDE for the particle displacement is

$$d\mathbf{X} = \left[\mathbf{V} + \theta^{-1}\nabla \cdot (\theta\mathbf{D})\right] dt + \mathbf{B} \cdot d\mathbf{W}$$

where $\mathbf{V}$ is the advective velocity, $\mathbf{D}$ the dispersion tensor, $\theta$ the porosity, $\mathbf{B}$ satisfies $\mathbf{B}\mathbf{B}^T = 2\mathbf{D}$, and $d\mathbf{W}$ is a Wiener process increment. Without the drift, particles collect where dispersion is low.

The GSDE obtains the drift without computing any gradient, by evaluating the dispersion at trial points with the same random numbers. Let $\lambda_n$ and $\mathbf{e}_n$ be the eigenvalues and unit eigenvectors of $2\mathbf{D}$, $\mathbf{S} = \sum_n \sqrt{\lambda_n}\, \mathbf{e}_n \mathbf{e}_n^T$ the symmetric square root of $2\mathbf{D}$, and $\Delta\mathbf{W} = \boldsymbol{\xi}\sqrt{\Delta t}$ with one $\boldsymbol{\xi} \sim \mathcal{N}(0, \mathbf{I})$ for the whole step. Then (LaBolle et al., 2000, eqs. 17a–17c)

$$\Delta\mathbf{Y} = \mathbf{S}(\mathbf{X})\,\Delta\mathbf{W}, \qquad \Delta\mathbf{U}_n = \sqrt{\lambda_n(\mathbf{X})}\,\Delta\mathbf{W}$$

$$\Delta\mathbf{X}_{disp} = \tfrac{1}{2}\sqrt{\frac{\theta(\mathbf{X}+\Delta\mathbf{Y})}{\theta(\mathbf{X})}}\;\mathbf{S}(\mathbf{X}+\Delta\mathbf{Y})\,\Delta\mathbf{W} \;+\; \tfrac{1}{2}\sum_n \mathbf{e}_n(\mathbf{X})\left[\mathbf{e}_n(\mathbf{X}) \cdot \sqrt{\frac{\theta(\mathbf{X}+\Delta\mathbf{U}_n)}{\theta(\mathbf{X})}}\;\mathbf{S}(\mathbf{X}+\Delta\mathbf{U}_n)\,\Delta\mathbf{W}\right]$$

For isotropic dispersion this reduces to $\Delta\mathbf{X}_{disp} = \mathbf{S}(\mathbf{X}+\Delta\mathbf{Y})\,\Delta\mathbf{W}$ (eq. 11a). Because no gradient is taken, jumps in dispersivity, porosity or velocity between cells are handled; the mean of the step is $\theta^{-1}\nabla\cdot(\theta\mathbf{D})\,\Delta t$.

**Trial points** are located by position: in the particle's layer, then in the wet cell below or above if the point lies outside the cell's saturated thickness, passing through dry cells as mod-PATH3DU does. If the first trial point $\mathbf{X}+\Delta\mathbf{Y}$ is outside the model, the step has no dispersive displacement; if a point $\mathbf{X}+\Delta\mathbf{U}_n$ is outside, the dispersion at the particle is used for it.

**Backward tracking** reverses advection but not the dispersive displacement: the backward process has the drift of the forward one.

### Dispersion Tensor

The tensor is the Burnett and Frind (1987) tensor of the mod-PATH3DU guide, with $|\mathbf{v}|$ the velocity magnitude and $v_{xy} = \sqrt{v_x^2 + v_y^2}$:

$$D_{xx} = \frac{\alpha_L v_x^2 + \alpha_{TH} v_y^2 + \alpha_{TV} v_z^2}{|\mathbf{v}|}, \quad D_{yy} = \frac{\alpha_L v_y^2 + \alpha_{TH} v_x^2 + \alpha_{TV} v_z^2}{|\mathbf{v}|}, \quad D_{zz} = \frac{\alpha_L v_z^2 + \alpha_{TV} v_{xy}^2}{|\mathbf{v}|}$$

$$D_{xy} = (\alpha_L - \alpha_{TH})\frac{v_x v_y}{|\mathbf{v}|}, \quad D_{xz} = (\alpha_L - \alpha_{TV})\frac{v_x v_z}{|\mathbf{v}|}, \quad D_{yz} = (\alpha_L - \alpha_{TV})\frac{v_y v_z}{|\mathbf{v}|}$$

Its principal directions are the flow direction $\mathbf{e}_0 = \mathbf{v}/|\mathbf{v}|$ with $\lambda_0 = 2\alpha_L|\mathbf{v}|$, the vertical transverse direction $\mathbf{e}_1 = (-v_x v_z, -v_y v_z, v_{xy}^2)/(|\mathbf{v}|\,v_{xy})$ with $\lambda_1 = 2\alpha_{TV}|\mathbf{v}|$, and the horizontal transverse direction $\mathbf{e}_2 = (-v_y, v_x, 0)/v_{xy}$ with $\lambda_2 = 2(\alpha_{TH} v_{xy}^2 + \alpha_{TV} v_z^2)/|\mathbf{v}|$. For purely vertical flow both horizontal directions take $\alpha_{TV}$.

### Example Configuration

```json
{
  "dispersion": {
    "method": "Gsde",
    "alpha_l": 10.0,
    "alpha_th": 1.0,
    "alpha_tv": 0.1
  }
}
```

!!! tip
    GSDE is preferred over Itô when simulations involve heterogeneous media with sharp property contrasts, or variable porosity, because it does not compute $\nabla \cdot \mathbf{D}$ numerically.

### Cost

Each step evaluates the velocity at the particle, at $\mathbf{X}+\Delta\mathbf{Y}$, and at one point $\mathbf{X}+\Delta\mathbf{U}_n$ for each direction with $\lambda_n > 0$: up to 5 evaluations, 4 in a two-dimensional model with $\alpha_{TV} = 0$.

### Deterministic Seeding

Random number generators are seeded deterministically by particle ID, not by thread identity. This ensures that trajectories are reproducible regardless of the number of parallel threads. Each particle uses 3 independent ChaCha8 streams, which give the one random vector of each step.

---

## Ito

Itô-Fokker-Planck dispersion method (LaBolle et al., 1996; Salamon et al., 2006). A single-step SDE method with explicit computation of the dispersion tensor divergence $\nabla \cdot \mathbf{D}$ via numerical central differences.

### Parameters

| Parameter | Schema Field | Type | Constraints | Description |
|-----------|-------------|------|-------------|-------------|
| Longitudinal dispersivity | `alpha_l` | number | ≥ 0 | Dispersivity parallel to flow direction [L] |
| Transverse horizontal dispersivity | `alpha_th` | number | ≥ 0 | Dispersivity perpendicular to flow in the horizontal plane [L] |
| Transverse vertical dispersivity | `alpha_tv` | number | ≥ 0 | Dispersivity perpendicular to flow in the vertical plane [L] |

### Mathematical Formulation

The Itô method directly solves:

$$\Delta \mathbf{X} = \left[\nabla \cdot \mathbf{D}\right] \Delta t + \mathbf{B} \cdot \boldsymbol{\xi} \sqrt{\Delta t}$$

where $\boldsymbol{\xi} \sim \mathcal{N}(0, \mathbf{I})$.

**Drift correction** $(\nabla \cdot \mathbf{D})$: Computed numerically via second-order central differences. For each spatial dimension $i$, the dispersion tensor is evaluated at $\mathbf{x} \pm \epsilon_i \hat{\mathbf{e}}_i$ and the divergence component is:

$$(\nabla \cdot \mathbf{D})_j = \frac{\partial D_{1j}}{\partial x_1} + \frac{\partial D_{2j}}{\partial x_2} + \frac{\partial D_{3j}}{\partial x_3}$$

Each partial derivative uses central differences:

$$\frac{\partial D_{ij}}{\partial x_k} \approx \frac{D_{ij}(\mathbf{x} + \epsilon_k \hat{\mathbf{e}}_k) - D_{ij}(\mathbf{x} - \epsilon_k \hat{\mathbf{e}}_k)}{2\epsilon_k}$$

with fallback to one-sided differences at domain boundaries.

**Brownian term:** Uses the velocity-aligned dispersion tensor, built from the velocity at the start of the step:

$$D_{ij} = D_L \, e_{1i} e_{1j} + D_{TH} \, e_{2i} e_{2j} + D_{TV} \, e_{3i} e_{3j}$$

where $(\mathbf{e}_1, \mathbf{e}_2, \mathbf{e}_3)$ is the velocity-aligned orthonormal frame below. It equals the GSDE's tensor when the flow is horizontal; when $v_z \neq 0$ the transverse directions differ.

**Limits:** the drift is $\nabla \cdot \mathbf{D}$, without the porosity ($\theta^{-1}\nabla \cdot (\theta\mathbf{D})$ in general), and the central differences straddle cell faces where the velocity, and so $\mathbf{D}$, can jump. Use the GSDE where porosity varies or the velocity field is discontinuous.

!!! info "Changed in 0.1.5"
    The tensor is built from the velocity at the start of the step, as the Itô scheme requires, instead of the step's average velocity; positions are global (z an elevation) and the vertical result is converted to the cell's local z; backward tracking keeps the sign of the drift. Results change slightly.

### Cost

The Itô method requires **8 extra velocity evaluations** per step (one at the particle, and seven for the central differences of $\nabla \cdot \mathbf{D}$), compared to up to 5 for GSDE.

### Example Configuration

```json
{
  "dispersion": {
    "method": "Ito",
    "alpha_l": 10.0,
    "alpha_th": 1.0,
    "alpha_tv": 0.1
  }
}
```

!!! warning "Performance"
    The Itô method is more expensive than GSDE because of the additional velocity evaluations per step for the numerical $\nabla \cdot \mathbf{D}$ computation.

### Deterministic Seeding

Each particle uses 3 independent ChaCha8 RNG streams (one per spatial dimension), seeded deterministically by particle ID.

---

## Velocity-Aligned Reference Frame (Itô)

The Itô method constructs a velocity-aligned orthonormal frame for rotating between local (dispersive) and global coordinates (the GSDE uses the principal directions of the Burnett–Frind tensor above):

| Direction | Basis Vector | Physical Meaning |
|-----------|-------------|------------------|
| $\mathbf{e}_1$ | $\mathbf{v} / \|\mathbf{v}\|$ | Longitudinal (parallel to flow) |
| $\mathbf{e}_2$ | $(0,0,1) \times \mathbf{e}_1$ (normalized) | Transverse horizontal |
| $\mathbf{e}_3$ | $\mathbf{e}_1 \times \mathbf{e}_2$ | Transverse vertical |

If the velocity is nearly vertical (parallel to $z$-up), the algorithm falls back to crossing with $(0,1,0)$ and then $(1,0,0)$ to avoid degenerate frames.

---

## References

- LaBolle, E. M., Quastel, J., Fogg, G. E., & Gravner, J. (2000). Diffusion processes in composite porous media and their numerical integration by random walks: Generalized stochastic differential equations with discontinuous coefficients. *Water Resources Research*, 36(3), 651–662.
- LaBolle, E. M., Fogg, G. E., & Tompson, A. F. B. (1996). Random-walk simulation of transport in heterogeneous porous media: Local mass-conservation problem and implementation methods. *Water Resources Research*, 32(3), 583–593.
- Salamon, P., Fernàndez-Garcia, D., & Gómez-Hernández, J. J. (2006). A review and numerical assessment of the random walk particle tracking method. *Journal of Contaminant Hydrology*, 87(3–4), 277–305.
- Burnett, R. D., & Frind, E. O. (1987). Simulation of contaminant transport in three dimensions: 2. Dimensionality effects. *Water Resources Research*, 23(4), 695–705.
