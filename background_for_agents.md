# mod-PATH3DU Documentation & Release Architecture

This document outlines the architecture and workflow for the mod-PATH3DU documentation platform and library distribution. It is designed to help AI agents and developers understand how the documentation is structured, built, and deployed.

## 1. The "Two-Repository" Strategy

To keep the proprietary source code completely private (local only) while allowing the public to read the documentation and download the compiled library, we use a two-repository strategy on GitHub:

1.  **`sspa-inc/mp3du-rs` (Public Release Repository):** This repository is public but contains **no source code**. It is used exclusively to host the compiled Python wheels (`.whl` files) in its GitHub Releases section.
2.  **`sspa-inc/mp3du-rs-docs` (Public Documentation Repository):** This repository is public and contains *only* the documentation files (`docs/` folder, `mkdocs.yml`). It hosts the live documentation website via GitHub Pages.

*Note: All actual C++ and Rust source code remains strictly local and is never pushed to GitHub.*

## 2. Documentation Framework

The documentation is built using **Material for MkDocs**, a static site generator written in Python.

*   **Configuration:** The main configuration file is `mkdocs.yml` located at the root of the `mp3du-rs-docs` repository. It defines the navigation structure, theme settings, and enabled plugins.
*   **Content:** All Markdown files (`.md`) are located in the `docs/` directory.
*   **Plugins:** We use several MkDocs plugins, notably:
    *   `mkdocstrings[python]`: Automatically generates API reference pages from Python type stubs (`.pyi` files).
    *   `pymdownx.snippets`: Allows injecting content from other files (like JSON schemas) directly into Markdown pages.
    *   `pymdownx.arithmatex`: Renders LaTeX math equations using KaTeX.

## 3. Automated Deployment (CI/CD)

The documentation is automatically built and deployed to **GitHub Pages** using GitHub Actions.

*   **Workflow File:** `.github/workflows/docs.yml` (in the `mp3du-rs-docs` repo).
*   **Trigger:** The workflow runs automatically whenever changes are pushed to the `main` branch of the docs repository.
*   **Process:**
    1.  Checks out the code.
    2.  Sets up Python and installs dependencies from `docs/requirements.txt`.
    3.  Runs custom Python scripts (`scripts/gen_*.py`) to generate dynamic content like the schema reference and `llms.txt`.
    4.  Runs `mkdocs build --strict` to compile the Markdown into HTML. The `--strict` flag ensures the build fails if there are any broken links or unlinked pages.
    5.  Uploads the built `site/` directory as an artifact.
    6.  Deploys the artifact to GitHub Pages.
*   **Live URL:** The documentation is hosted at `https://sspa-inc.github.io/mp3du-rs-docs/`.

## 4. Python API Reference (`mkdocstrings`)

The API reference pages (e.g., `ParticleStart`, `SimulationConfig`) are generated automatically from Python type stubs.

*   **Stub Location:** The type stubs are located in `docs/_stubs/mp3du/__init__.pyi` within the `mp3du-rs-docs` repository.
*   **How it works:** A Markdown page like `docs/reference/python-api/ParticleStart.md` contains a special directive: `::: mp3du.ParticleStart`. When MkDocs builds the site, the `mkdocstrings` plugin reads the `__init__.pyi` file, extracts the signature and docstrings for `ParticleStart`, and replaces the directive with the generated HTML.
*   **Maintenance Rule:** Whenever the Rust/Python API changes in the local source code, the updated `.pyi` stub file must be manually copied over to `docs/_stubs/mp3du/__init__.pyi` in the public `mp3du-rs-docs` repository to keep the documentation accurate.

## 5. AI-Agent Accessibility

The documentation is designed to be easily readable by AI agents (like Copilot or Cursor).

*   **`llms.txt`:** A condensed, plain-text summary of the project, key types, and links, located at the root of the site (`https://sspa-inc.github.io/mp3du-rs-docs/llms.txt`).
*   **`llms-full.txt`:** An expanded version containing the complete JSON schema, Python type stubs, and minimal/complete configuration examples.
*   **Raw Artifacts:** The raw JSON schema and type stubs are also available in the `docs/assets/raw/` directory for direct ingestion by agents.

## 6. Releasing the Compiled Library

Because mod-PATH3DU is proprietary freeware, it is not published to PyPI. The compiled Python library (`.whl` file) is distributed via GitHub Releases on the public `mp3du-rs` repository.

*   **Build Process:** The `.whl` file is built locally from the private source code using `maturin build --release` (or via the `scripts/build_python_wheel.py` script).
*   **Distribution:** The built `.whl` file is manually uploaded to a new Release on the public `sspa-inc/mp3du-rs` repository.
*   **Installation:** Users install the library directly from the release URL using `pip install <url-to-wheel>`. The installation instructions in the documentation (`docs/getting-started/install.md`) reflect this process.