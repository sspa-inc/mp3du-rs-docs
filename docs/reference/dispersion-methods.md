# Dispersion Methods

mod-PATH3DU supports three dispersion modes for stochastic particle tracking. When dispersion is enabled, random perturbations are added to particle velocities to simulate mechanical dispersion in porous media.

## Dispersion Mode Comparison

| Mode | Stochastic | Parameters Required | Velocity Evaluations | Use Case |
|------|-----------|--------------------|-----------------------|----------|
| None | No | — | 0 extra | Advection-only tracking |
| Gsde | Yes | Dispersivities, [per cell or in the configuration](#giving-the-dispersivities) | Up to 5 extra (the particle and the trial points) | Standard dispersive transport — robust at material interfaces |
| Ito | Yes | Dispersivities, [per cell or in the configuration](#giving-the-dispersivities), the same in every cell | 8 extra (the particle and the numerical $\nabla \cdot \mathbf{D}$) | Itô SDE with explicit drift correction, for smooth fields |

!!! info "Schema Values"
    Dispersion method values in the JSON Schema: `"None"`, `"Gsde"`, `"Ito"`.

---

## Giving the Dispersivities

The three dispersivities, longitudinal ($\alpha_L$), horizontal transverse ($\alpha_{TH}$) and vertical transverse ($\alpha_{TV}$), are lengths in the model's length unit. They are given in one of two ways, and a run uses exactly one of them:

| | Per cell | In the configuration |
|---|---|---|
| Given as | the arrays `disp_long`, `disp_trans_h` and `disp_trans_v`, one value per cell | the numbers `alpha_l`, `alpha_th` and `alpha_tv` in the `dispersion` block |
| Passed to | `hydrate_cell_properties()` for MODFLOW models (`fit_waterloo()`); `hydrate_sspa_inputs()` for MEUK models (`fit_sspa()`) | `SimulationConfig.from_json()` |
| Values | may differ from cell to cell, by layer or zone; for one value everywhere, fill the arrays with it, for example `np.full(n_cells, 10.0)` | the same in every cell |
| The other place | `alpha_l`, `alpha_th` and `alpha_tv` left out of the `dispersion` block | the three arrays left out |
| In mod-PATH3DU | for MODFLOW models, the three dispersivity arrays of the `.p3d` file (labelled `DISPH`, `DISPT` and `DISPV` in the Example 5a input), which mod-PATH3DU uses as the longitudinal, horizontal transverse and vertical transverse dispersivities. mod-PATH3DU has no per-cell dispersivities for MEUK models; MP3DU-RS adds them | for MEUK models, `LONGITUDINAL` and `TRANSVERSE_HORIZONTAL` in the `DISPERSION` block of the model's JSON, which are `alpha_l` and `alpha_th`; mod-PATH3DU sets the vertical transverse dispersivity to 0 |

Per cell, for example 10 m in the top layer and 1 m in the layers below it (`layer` holds the layer index of each cell):

```python
props = mp3du.hydrate_cell_properties(
    top=top, bot=bot, porosity=porosity, retardation=retardation, hhk=hhk, vhk=vhk,
    disp_long=np.where(layer == 0, 10.0, 1.0),
    disp_trans_h=np.where(layer == 0, 1.0, 0.1),
    disp_trans_v=np.full(n_cells, 0.01),
)
config_dict["dispersion"] = {"method": "Gsde"}   # no alpha_l, alpha_th or alpha_tv
```

In the configuration, the same values in every cell:

```python
props = mp3du.hydrate_cell_properties(
    top=top, bot=bot, porosity=porosity, retardation=retardation, hhk=hhk, vhk=vhk,
)                                                 # no dispersivity arrays
config_dict["dispersion"] = {"method": "Gsde", "alpha_l": 10.0, "alpha_th": 1.0, "alpha_tv": 0.01}
```

For a MEUK model (`fit_sspa()`) the same two ways apply, with `hydrate_sspa_inputs()`, and the vertical transverse dispersivity must be 0:

```python
inputs = mp3du.hydrate_sspa_inputs(                # per cell
    heads=heads, porosity=porosity, well_mask=well_mask, hhk=hhk,
    disp_long=np.full(n_cells, 100.0),
    disp_trans_h=np.full(n_cells, 10.0),
    disp_trans_v=np.zeros(n_cells),                 # must be 0 for SSP&A
)
config_dict["dispersion"] = {"method": "Gsde"}

inputs = mp3du.hydrate_sspa_inputs(                # or in the configuration
    heads=heads, porosity=porosity, well_mask=well_mask, hhk=hhk,
)
config_dict["dispersion"] = {"method": "Gsde", "alpha_l": 100.0, "alpha_th": 10.0, "alpha_tv": 0.0}
```

The arrays are in cell-id order, like every other per-cell array, and any values per cell work: from a zone array `zone` that holds 0, 1 or 2 for each cell, for example, `disp_long = np.array([10.0, 1.0, 30.0])[zone]`.

!!! danger "One place at a time"
    With dispersion on, `run_simulation()` raises `ValueError` before it tracks any particle if the dispersivities are given in both places, or in neither:

    - both: *dispersivity is given twice: as alpha_l, alpha_th and alpha_tv in the configuration's dispersion block, and per cell as disp_long, disp_trans_h and disp_trans_v (to hydrate_cell_properties() or hydrate_sspa_inputs()). Use one of them: ...*
    - neither: *dispersion is on but no dispersivity is given. ...*

    Giving only one or two of the three arrays, or of the three numbers, is also an error. `SimulationConfig.validate()` sees the configuration alone, so it cannot tell whether the model's inputs also give the dispersivities; `run_simulation()` checks that.

    With `"method": "None"` no dispersivity is used. Per-cell arrays may still be given; if any of their values is not 0, `run_simulation()` issues a `UserWarning` that they are not used. Arrays of zeros, which scripts for 0.1.5 pass because it required them, are accepted silently.

Every value must be finite and not negative, in every cell, inactive and dry cells included. With the GSDE, fill those with any valid value, such as 0; with Itô, give them the same values as every other cell. Two more rules apply:

- **Itô** needs the same dispersivities in every cell. It takes its drift from differences of the dispersion tensor, which cannot represent a change of dispersivity from one cell to the next, so per-cell values that differ between cells are refused, even if they differ only in the last digit or only in inactive cells. Use the GSDE for them, or give one set in the configuration.
- **MEUK models** (`fit_sspa()`) are two-dimensional, so the vertical transverse dispersivity, `alpha_tv` or `disp_trans_v`, must be 0. mod-PATH3DU also sets it to 0 for MEUK models.

With per-cell values, the dispersion at the particle uses the dispersivities of the particle's cell, and each trial point of the GSDE uses those of the cell it lies in, as in mod-PATH3DU. The GSDE then produces the drift across a change of dispersivity between layers or zones. This follows mod-PATH3DU's algorithm; results with dispersivity zones have not yet been compared with mod-PATH3DU's.

The [error messages](error-diagnostics.md#dispersivity-errors) are listed with their remedies.

!!! warning "Changed in 0.1.6"
    Before 0.1.6 the configuration's values were used in every cell, and the per-cell arrays, which `hydrate_cell_properties()` required, were not used. A script that passes the arrays and also gives the configuration's values now stops with the *given twice* error. To keep the results of 0.1.5, which used the configuration's values, remove the arrays; scripts that passed arrays of zeros, as the earlier examples did, need nothing else. To use the per-cell values instead, remove `alpha_l`, `alpha_th` and `alpha_tv` from the `dispersion` block. A MEUK script with `alpha_tv` other than 0 now stops too; set it to 0 (in 0.1.5 it moved particles out of the model).

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

The three numbers are given together or not at all: all three for the same dispersivities in every cell, or none of them, with the dispersivities given per cell instead (see [Giving the Dispersivities](#giving-the-dispersivities)).

### Mathematical Formulation

A random walk reproduces the advection-dispersion equation only when a drift is added to the random step. The Itô SDE for the particle displacement is

$$d\mathbf{X} = \left[\mathbf{V} + \theta^{-1}\nabla \cdot (\theta\mathbf{D})\right] dt + \mathbf{B} \cdot d\mathbf{W}$$

where $\mathbf{V}$ is the advective velocity, $\mathbf{D}$ the dispersion tensor, $\theta$ the porosity, $\mathbf{B}$ satisfies $\mathbf{B}\mathbf{B}^T = 2\mathbf{D}$, and $d\mathbf{W}$ is a Wiener process increment. Without the drift, particles collect where dispersion is low.

The GSDE obtains the drift without computing any gradient, by evaluating the dispersion at trial points with the same random numbers. Let $\lambda_n$ and $\mathbf{e}_n$ be the eigenvalues and unit eigenvectors of $2\mathbf{D}$, $\mathbf{S} = \sum_n \sqrt{\lambda_n}\, \mathbf{e}_n \mathbf{e}_n^T$ the symmetric square root of $2\mathbf{D}$, and $\Delta\mathbf{W} = \boldsymbol{\xi}\sqrt{\Delta t}$ with one $\boldsymbol{\xi} \sim \mathcal{N}(0, \mathbf{I})$ for the whole step. Then (LaBolle et al., 2000, eqs. 17a–17c)

$$\Delta\mathbf{Y} = \mathbf{S}(\mathbf{X})\,\Delta\mathbf{W}, \qquad \Delta\mathbf{U}_n = \sqrt{\lambda_n(\mathbf{X})}\,\Delta\mathbf{W}$$

$$\Delta\mathbf{X}_{disp} = \tfrac{1}{2}\sqrt{\frac{\theta(\mathbf{X}+\Delta\mathbf{Y})}{\theta(\mathbf{X})}}\;\mathbf{S}(\mathbf{X}+\Delta\mathbf{Y})\,\Delta\mathbf{W} \;+\; \tfrac{1}{2}\sum_n \mathbf{e}_n(\mathbf{X})\left[\mathbf{e}_n(\mathbf{X}) \cdot \sqrt{\frac{\theta(\mathbf{X}+\Delta\mathbf{U}_n)}{\theta(\mathbf{X})}}\;\mathbf{S}(\mathbf{X}+\Delta\mathbf{U}_n)\,\Delta\mathbf{W}\right]$$

For isotropic dispersion this reduces to $\Delta\mathbf{X}_{disp} = \mathbf{S}(\mathbf{X}+\Delta\mathbf{Y})\,\Delta\mathbf{W}$ (eq. 11a). Because no gradient is taken, jumps in dispersivity or velocity between cells are handled. Where porosity varies smoothly the mean of the step is $\theta^{-1}\nabla\cdot(\theta\mathbf{D})\,\Delta t$; at a jump in porosity between layers it is not, and too many particles collect on the side of lower porosity (see the known issue in [Layers and Boundaries](../concepts/dispersion-theory.md#layers-and-boundaries)).

**Trial points** are reached the way the displacement itself is: vertically through the wet cells, measured in each cell's saturated thickness, then horizontally across the cells of the layer reached, keeping the particle's position within the layer's thickness. At a face or edge with no wet cell beyond (the top or bottom of the model, a dry or inactive cell, the edge of the grid) the path is reflected, so a trial point beyond it is taken at its mirror image: the dispersion is extended evenly across the wall, which makes the reflected random walk exact where the flow runs along the wall. Each trial point takes the dispersivities and porosity of the cell it lies in. Up to 0.1.7 trial points were located by elevation, a first trial point $\mathbf{X}+\Delta\mathbf{Y}$ outside the model dropped the whole displacement, and one beyond a top or bottom face was evaluated on the face.

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
    GSDE is preferred over Itô where dispersivity or velocity changes sharply, or porosity varies, because it does not compute $\nabla \cdot \mathbf{D}$ numerically. It is the method to use for dispersivities that differ between cells, which Itô refuses. At a jump in porosity between layers it has a known bias (see [Layers and Boundaries](../concepts/dispersion-theory.md#layers-and-boundaries)).

### Cost

Each step evaluates the velocity at the particle, at $\mathbf{X}+\Delta\mathbf{Y}$, and at one point $\mathbf{X}+\Delta\mathbf{U}_n$ for each direction with $\lambda_n > 0$: up to 5 evaluations, 4 in a two-dimensional model with $\alpha_{TV} = 0$.

### Deterministic Seeding

Random number generators are seeded deterministically by particle ID, not by thread identity. This ensures that trajectories are reproducible on the same computer, regardless of the number of parallel threads; between platforms they can differ (see [Results on Different Platforms](../getting-started/install.md#results-on-different-platforms)). Each particle uses 3 independent ChaCha8 streams, which give the one random vector of each step.

---

## Ito

Itô-Fokker-Planck dispersion method (LaBolle et al., 1996; Salamon et al., 2006). A single-step SDE method with explicit computation of the dispersion tensor divergence $\nabla \cdot \mathbf{D}$ via numerical central differences.

### Parameters

| Parameter | Schema Field | Type | Constraints | Description |
|-----------|-------------|------|-------------|-------------|
| Longitudinal dispersivity | `alpha_l` | number | ≥ 0 | Dispersivity parallel to flow direction [L] |
| Transverse horizontal dispersivity | `alpha_th` | number | ≥ 0 | Dispersivity perpendicular to flow in the horizontal plane [L] |
| Transverse vertical dispersivity | `alpha_tv` | number | ≥ 0 | Dispersivity perpendicular to flow in the vertical plane [L] |

As for the GSDE, the three numbers are given together or not at all, with the dispersivities then given per cell; per-cell values must be the same in every cell for Itô (see [Giving the Dispersivities](#giving-the-dispersivities)).

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

**Limits:** the drift is $\nabla \cdot \mathbf{D}$, without the porosity ($\theta^{-1}\nabla \cdot (\theta\mathbf{D})$ in general), and differences cannot represent a jump in $\mathbf{D}$, or in its principal directions, between cells. At a face between layers of different velocity Itô gathers particles on the side of lower dispersion (0.24 to 0.35 instead of 0.5 in a test with the dispersion four times higher in one of two layers). Use the GSDE where porosity varies or the velocity field is discontinuous (it too has a known bias at a jump in porosity; see [Layers and Boundaries](../concepts/dispersion-theory.md#layers-and-boundaries)). For the same reason Itô refuses per-cell dispersivities that differ between cells: such a run stops with a `ValueError`.

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

Each particle uses 3 independent ChaCha8 RNG streams (one per spatial dimension), seeded deterministically by particle ID. As with the GSDE, trajectories are reproducible on the same computer but can differ between platforms (see [Results on Different Platforms](../getting-started/install.md#results-on-different-platforms)).

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
- LaBolle, E. M., & Zhang, Y. (2006). Reply to comment by D.-H. Lim on "Diffusion processes in composite porous media and their numerical integration by random walks: Generalized stochastic differential equations with discontinuous coefficients". *Water Resources Research*, 42, W02602. doi:10.1029/2005WR004403
- LaBolle, E. M., Fogg, G. E., & Tompson, A. F. B. (1996). Random-walk simulation of transport in heterogeneous porous media: Local mass-conservation problem and implementation methods. *Water Resources Research*, 32(3), 583–593.
- Salamon, P., Fernàndez-Garcia, D., & Gómez-Hernández, J. J. (2006). A review and numerical assessment of the random walk particle tracking method. *Journal of Contaminant Hydrology*, 87(3–4), 277–305.
- Burnett, R. D., & Frind, E. O. (1987). Simulation of contaminant transport in three dimensions: 2. Dimensionality effects. *Water Resources Research*, 23(4), 695–705.
