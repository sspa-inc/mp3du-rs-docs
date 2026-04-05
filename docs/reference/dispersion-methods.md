# Dispersion Methods

mod-PATH3DU supports three dispersion modes for stochastic particle tracking. When dispersion is enabled, random perturbations are added to particle velocities to simulate mechanical dispersion in porous media.

## Dispersion Mode Comparison

| Mode | Stochastic | Parameters Required | Velocity Evaluations | Use Case |
|------|-----------|--------------------|-----------------------|----------|
| None | No | — | 0 extra | Advection-only tracking |
| Gsde | Yes | `alpha_l`, `alpha_th`, `alpha_tv` | 1 extra (displaced position) | Standard dispersive transport — robust at material interfaces |
| Ito | Yes | `alpha_l`, `alpha_th`, `alpha_tv` | 6 extra (numerical $\nabla \cdot \mathbf{D}$) | Full Itô SDE with explicit drift correction |

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

Generalized Stochastic Differential Equation two-step method (LaBolle et al., 2000). This is the recommended dispersion method for most simulations.

### Parameters

| Parameter | Schema Field | Type | Constraints | Description |
|-----------|-------------|------|-------------|-------------|
| Longitudinal dispersivity | `alpha_l` | number | ≥ 0 | Dispersivity parallel to flow direction [L] |
| Transverse horizontal dispersivity | `alpha_th` | number | ≥ 0 | Dispersivity perpendicular to flow in the horizontal plane [L] |
| Transverse vertical dispersivity | `alpha_tv` | number | ≥ 0 | Dispersivity perpendicular to flow in the vertical plane [L] |

### Mathematical Formulation

The GSDE method solves the stochastic advection-dispersion equation using a two-step random walk that avoids computing the dispersion tensor gradient $\nabla \cdot \mathbf{D}$.

The general Itô SDE for particle displacement is:

$$d\mathbf{X} = \left[\mathbf{V} + \nabla \cdot \mathbf{D}\right] dt + \mathbf{B} \cdot d\mathbf{W}$$

where $\mathbf{V}$ is the advective velocity, $\mathbf{D}$ is the dispersion tensor, $\mathbf{B}$ satisfies $\mathbf{B}\mathbf{B}^T = 2\mathbf{D}$, and $d\mathbf{W}$ is a Wiener process increment.

The GSDE two-step method eliminates the $\nabla \cdot \mathbf{D}$ term (which is undefined at material interfaces) by evaluating dispersion at two positions:

**Step 1 — Trial displacement** (LaBolle eq. 11a):

$$\Delta \mathbf{Y} = \mathbf{B}(\mathbf{x}) \cdot \boldsymbol{\xi}_1 \sqrt{\Delta t}$$

where $\boldsymbol{\xi}_1 \sim \mathcal{N}(0, \mathbf{I})$.

**Step 2 — Actual displacement** (LaBolle eq. 11b):

$$\Delta \mathbf{X} = \mathbf{B}(\mathbf{x} + \Delta \mathbf{Y}) \cdot \boldsymbol{\xi}_2 \sqrt{\Delta t}$$

The accepted displacement is $\Delta \mathbf{X}$ from step 2 only. This two-evaluation trick implicitly accounts for the drift correction.

### Dispersion Tensor Construction

In the velocity-aligned reference frame, the local dispersion coefficients are diagonal:

$$D_L = \alpha_L \|\mathbf{v}\|, \quad D_{TH} = \alpha_{TH} \|\mathbf{v}\|, \quad D_{TV} = \alpha_{TV} \|\mathbf{v}\|$$

The Brownian displacement in local coordinates is:

$$\Delta X_L = \sqrt{2 D_L \Delta t} \; \xi_1, \quad \Delta X_{TH} = \sqrt{2 D_{TH} \Delta t} \; \xi_2, \quad \Delta X_{TV} = \sqrt{2 D_{TV} \Delta t} \; \xi_3$$

These are rotated to global coordinates using the velocity-aligned orthonormal frame $(\mathbf{e}_1, \mathbf{e}_2, \mathbf{e}_3)$ where $\mathbf{e}_1$ is the longitudinal direction (parallel to $\mathbf{v}$).

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
    GSDE is preferred over Itô when simulations involve heterogeneous media with sharp property contrasts, because it does not require computing $\nabla \cdot \mathbf{D}$ numerically.

### Deterministic Seeding

Random number generators are seeded deterministically by particle ID, not by thread identity. This ensures that trajectories are reproducible regardless of the number of parallel threads. Each particle uses 6 independent ChaCha8 RNG streams (3 for the trial step, 3 for the actual step).

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

**Brownian term:** Uses the same velocity-aligned Burnett-Frind dispersion tensor as GSDE:

$$D_{ij} = D_L \, e_{1i} e_{1j} + D_{TH} \, e_{2i} e_{2j} + D_{TV} \, e_{3i} e_{3j}$$

where $(\mathbf{e}_1, \mathbf{e}_2, \mathbf{e}_3)$ is the velocity-aligned orthonormal frame.

### Cost

The Itô method requires **6 extra velocity evaluations** per step (two per spatial dimension for central differences) compared to 1 extra for GSDE.

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
    The Itô method is significantly more expensive than GSDE due to the 6 additional velocity evaluations per step for the numerical $\nabla \cdot \mathbf{D}$ computation.

### Deterministic Seeding

Each particle uses 3 independent ChaCha8 RNG streams (one per spatial dimension), seeded deterministically by particle ID.

---

## Velocity-Aligned Reference Frame

Both GSDE and Itô construct a velocity-aligned orthonormal frame for rotating between local (dispersive) and global coordinates:

| Direction | Basis Vector | Physical Meaning |
|-----------|-------------|------------------|
| $\mathbf{e}_1$ | $\mathbf{v} / \|\mathbf{v}\|$ | Longitudinal (parallel to flow) |
| $\mathbf{e}_2$ | $(0,0,1) \times \mathbf{e}_1$ (normalized) | Transverse horizontal |
| $\mathbf{e}_3$ | $\mathbf{e}_1 \times \mathbf{e}_2$ | Transverse vertical |

If the velocity is nearly vertical (parallel to $z$-up), the algorithm falls back to crossing with $(0,1,0)$ and then $(1,0,0)$ to avoid degenerate frames.

---

## References

- LaBolle, E. M., Fogg, G. E., & Tompson, A. F. B. (2000). Random-walk simulation of transport in heterogeneous porous media: Local mass-conservation problem and implementation methods. *Water Resources Research*, 36(4), 583–593.
- LaBolle, E. M., Fogg, G. E., & Tompson, A. F. B. (1996). Random-walk simulation of solute transport in heterogeneous porous media: An approach using Itô stochastic calculus. *Water Resources Research*, 32(3), 583–593.
- Salamon, P., Fernàndez-Garcia, D., & Gómez-Hernández, J. J. (2006). A review and numerical assessment of the random walk particle tracking method. *Journal of Contaminant Hydrology*, 87(3–4), 277–305.
- Burnett, R. D., & Frind, E. O. (1987). Simulation of contaminant transport in three dimensions: 2. Dimensionality effects. *Water Resources Research*, 23(4), 695–705.
