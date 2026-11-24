# mod-PATH3DU

**3D particle tracking engine for groundwater flow models.**

mod-PATH3DU is a modernized particle tracking engine built in Rust with Python bindings via PyO3. It supports unstructured grids (MODFLOW-USG), adaptive Runge-Kutta integration, the Waterloo method and SSP&A (Papadopulos) method for velocity interpolation, and stochastic dispersion (GSDE and Ito formulations), with dispersivities given per cell or once for the whole model.

!!! info "User's Guide"
    The User's Guide for mod-PATH3DU is at [mp3du.sspa.com/man](https://mp3du.sspa.com/man/index.html), on the mod-PATH3DU website, [mp3du.sspa.com](https://mp3du.sspa.com/). It explains the method, its background and its limitations, and works through examples with figures. Its input instructions are for the Windows executable, `mp3du.exe`; the Python package is documented on this site.

## Quick Links

- [Installation](getting-started/install.md) — Get up and running
- [Quickstart](getting-started/quickstart.md) — Your first simulation in Python
- [Schema Reference](reference/schema-reference.md) — Full configuration contract
- [Python API](reference/python-api/index.md) — Type signatures and class reference
- [Examples](examples/index.md) — Validated, copy-paste-ready examples
- [SSP&A Workflow](guides/sspa-workflow.md) — Particle tracking from head maps

## AI Agent Resources

> **Using ChatGPT, Claude, Copilot, Cursor, or another coding agent?**
> Start with the [AI Agent Prompts](guides/agent-prompts.md) guide for copy-paste prompts,
> then use the machine-readable references below.

### For AI Agents

Machine-readable references are available at:

- [`AI Agent Prompts`](guides/agent-prompts.md) — Copy-paste prompts for MODFLOW and raster / MEUK / SSP&A workflows
- [`llms.txt`](llms.txt) — Condensed project summary (< 4KB)
- [`llms-full.txt`](llms-full.txt) — Complete schema, stubs, and examples
- Raw artifacts — Direct access to `.pyi` stubs and JSON Schema (available after deployment)
