# Installation

Get mod-PATH3DU installed and ready to use.

## Prerequisites

- **Python** ≥ 3.8, 64-bit
- **pip** (included with Python)
- **NumPy**, installed by the first command below
- **Platform**, one of:
    - Windows, 64-bit (x86-64)
    - macOS on Apple Silicon, macOS 11 or later
    - macOS on Intel, macOS 10.12 or later
    - Linux, x86-64, with glibc 2.17 or later (manylinux2014)

## Install with pip

mod-PATH3DU is proprietary freeware and is not published on PyPI. Its wheels are attached to the releases on the [GitHub Releases page](https://github.com/sspa-inc/mp3du-rs/releases), and SSP&A's package index lists them so that pip picks the wheel for your platform. The same two commands install it on every platform:

```bash
pip install numpy
pip install mp3du-py --index-url https://sspa-inc.github.io/mp3du-rs/simple/
```

To install a particular version, add it to the package name, for example `mp3du-py==0.1.6`. To update an existing installation to the latest version, add `--upgrade` to the second command. Neither changes the installed NumPy.

!!! warning "Keep the two commands separate"
    Run the two commands as given. Do not combine them into one, and do not replace `--index-url` with `--extra-index-url`. `mp3du-py` is not on PyPI, and a pip command that searches PyPI as well as SSP&A's index takes the highest version it finds in either, so a package published on PyPI under the same name could be installed in place of mod-PATH3DU.

If the second command reports `No matching distribution found for numpy`, NumPy is not installed: run the first command and try again.

!!! tip "Virtual environment recommended"
    Install Python packages into a virtual environment to avoid conflicts with other packages:

    ```bash
    python -m venv .venv
    .venv\Scripts\activate          # Windows
    source .venv/bin/activate       # macOS and Linux
    pip install numpy
    pip install mp3du-py --index-url https://sspa-inc.github.io/mp3du-rs/simple/
    ```

### Install a Downloaded Wheel

To install from a file instead, download the wheel for your platform from the [Releases page](https://github.com/sspa-inc/mp3du-rs/releases) and give its path to pip:

```bash
pip install numpy
pip install path/to/mp3du_py-0.1.6-cp38-abi3-win_amd64.whl
```

The end of each wheel's name gives its platform: `win_amd64` (Windows), `macosx_11_0_arm64` (macOS on Apple Silicon), `macosx_10_12_x86_64` (macOS on Intel) and `manylinux_2_17_x86_64.manylinux2014_x86_64` (Linux).

## Verify Installation

Open a Python interpreter and confirm the module loads:

```python
import mp3du
print(mp3du.version())
```

You should see a version string like `0.1.6`. If the import succeeds, the installation is complete.

!!! tip
    If the import fails with `ModuleNotFoundError`, ensure you are in the correct virtual environment and the package is installed (`pip list | findstr mp3du` on Windows, `pip list | grep mp3du` on macOS and Linux).

## Results on Different Platforms

On one computer, a run repeated with the same inputs and the same version of mod-PATH3DU gives the same results, whatever the number of parallel threads. Between platforms, results can differ slightly, because each operating system's maths library (`ln`, `exp`, `sin` and the like) can differ in the last bits of a result. Where such a difference changes a step-size decision or a cell crossing, an advective path can differ by an amount of the order of the solver's error tolerance. With dispersion, the rest of that particle's path then becomes a different random realization, although the random numbers are seeded by particle ID. Compare runs made on different platforms by their statistics, such as concentrations or capture fractions, not particle by particle.

## What's Next?

- [Quickstart](quickstart.md) — Run your first particle tracking simulation
