# mod-PATH3DU

**3D particle tracking engine for groundwater flow models.**

mod-PATH3DU is a modernized particle tracking engine built in Rust with Python bindings via PyO3. It supports unstructured grids (MODFLOW-USG), adaptive Runge-Kutta integration, the Waterloo method and SSP&A (Papadopulos) method for velocity interpolation, and stochastic dispersion (GSDE and Ito formulations).

## Quick Links

- [Installation](getting-started/install.md) — Get up and running
- [Quickstart](getting-started/quickstart.md) — Your first simulation in Python
- [Schema Reference](reference/schema-reference.md) — Full configuration contract
- [Python API](reference/python-api/index.md) — Type signatures and class reference
- [Examples](examples/index.md) — Validated, copy-paste-ready examples
- [SSP&A Workflow](guides/sspa-workflow.md) — Particle tracking from head maps

## For AI Agents

Machine-readable references are available at:

- [`llms.txt`](llms.txt) — Condensed project summary (< 4KB)
- [`llms-full.txt`](llms-full.txt) — Complete schema, stubs, and examples
- Raw artifacts — Direct access to `.pyi` stubs and JSON Schema (available after deployment)
