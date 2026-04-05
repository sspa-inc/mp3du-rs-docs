# Installation

Get mod-PATH3DU installed and ready to use.

## Prerequisites

- **Python** ≥ 3.8
- **pip** (included with Python)
- **NumPy** (installed automatically as a dependency)
- **Platform:** Windows (64-bit)

## Install from GitHub Releases

Because mod-PATH3DU is a proprietary freeware library, it is not hosted on PyPI. Instead, you can download and install the compiled Python wheel (`.whl`) directly from the official GitHub repository.

### Step 1: Find the Latest Release
Go to the [mod-PATH3DU Releases Page](https://github.com/sspa-inc/mp3du-rs-docs/releases) and find the latest version.

### Step 2: Install via pip
You can install the `.whl` file directly using its URL. Right-click the `.whl` file in the release assets, copy the link address, and run:

```bash
pip install https://github.com/sspa-inc/mp3du-rs-docs/releases/download/v0.1.0/mp3du_py-0.1.0-cp38-abi3-win_amd64.whl
```
*(Note: Replace the URL above with the actual link to the latest release).*

Alternatively, you can download the `.whl` file to your computer and install it locally:

```bash
pip install path/to/downloaded/mp3du_py-0.1.0-cp38-abi3-win_amd64.whl
```

!!! tip "Virtual environment recommended"
    It is always recommended to install Python packages into a virtual environment to avoid conflicts with system packages:

    ```bash
    python -m venv .venv
    .venv\Scripts\activate
    pip install <url-or-path-to-wheel>
    ```

## Verify Installation

Open a Python interpreter and confirm the module loads:

```python
import mp3du
print(mp3du.version())
```

You should see a version string like `0.1.0`. If the import succeeds, the installation is complete.

!!! tip
    If the import fails with `ModuleNotFoundError`, ensure you are in the correct virtual environment and the package is installed (`pip list | findstr mp3du`).

## What's Next?

- [Quickstart](quickstart.md) — Run your first particle tracking simulation
