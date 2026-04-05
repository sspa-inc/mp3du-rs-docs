# mod-PATH3DU — Documentation

This repository contains the documentation for **mp3du-rs**, a Python API for mod-PATH3DU — a 3D particle tracking engine for groundwater flow models.

mod-PATH3DU supports both structured and horizontally-unstructured, vertically-layered grids, and is compatible with all major versions of MODFLOW. The API was designed and implemented in collaboration with AI, using a custom MCP server to ground every algorithmic decision in the original C++ codebase, which has years of real-world use behind it.

**Early release.** The mp3du-rs Python API is available for testing and evaluation, but has not yet undergone the same level of rigorous validation as the original C++ version. Results should be checked against known solutions before use in production work. Feedback and bug reports welcome via [GitHub Issues](https://github.com/sspa-inc/mp3du-rs/issues).

## Documentation

**https://sspa-inc.github.io/mp3du-rs-docs/**

For AI agents: [`llms.txt`](https://sspa-inc.github.io/mp3du-rs-docs/llms.txt) · [`llms-full.txt`](https://sspa-inc.github.io/mp3du-rs-docs/llms-full.txt)

## Library

The compiled Python wheel is distributed separately at [sspa-inc/mp3du-rs](https://github.com/sspa-inc/mp3du-rs).

