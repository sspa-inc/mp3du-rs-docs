# Installation

Get mod-PATH3DU installed and ready to use.

## Prerequisites

- **Python** ≥ 3.9
- **pip** (included with Python)
- **NumPy** (installed automatically as a dependency)
- **Platform:** Windows, macOS, or Linux

## Install from PyPI

```bash
pip install mp3du
```

!!! note
    If the package is not yet published to PyPI, install from a local wheel or build from source (see below).

## Build from Source

If you need the latest development version or the package is not yet on PyPI, build directly from the Rust source.

### Requirements

- **Rust** ≥ 1.75.0 — install from [rustup.rs](https://rustup.rs/)
- **maturin** — the Python/Rust build tool

```bash
pip install maturin
```

### Steps

=== "Development (editable)"

    Build and install in the current virtual environment:

    ```bash
    cd rust-micro-kernel
    maturin develop --release
    ```

=== "Wheel (distributable)"

    Build a wheel for distribution:

    ```bash
    cd rust-micro-kernel
    maturin build --release
    pip install target/wheels/mp3du-*.whl
    ```

!!! tip "Virtual environment recommended"
    Always install into a virtual environment to avoid conflicts with system packages:

    ```bash
    python -m venv .venv
    .venv\Scripts\activate   # Windows
    source .venv/bin/activate # macOS / Linux
    ```

## Verify Installation

Open a Python interpreter and confirm the module loads:

```python
import mp3du
print(mp3du.version())
```

You should see a version string like `0.1.0`. If the import succeeds, the installation is complete.

!!! tip
    If the import fails with `ModuleNotFoundError`, ensure you are in the correct virtual environment and the package is installed (`pip list | findstr mp3du` on Windows, or `pip list | grep mp3du` on macOS/Linux).

## What's Next?

- [Quickstart](quickstart.md) — Run your first particle tracking simulation
