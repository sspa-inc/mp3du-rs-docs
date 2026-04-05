# AI Agent Prompts

Because `mp3du` is a specialized, modern particle tracking engine with strict
data-loading conventions, general-purpose AI assistants can easily fall back to
older MODPATH habits and produce plausible-looking but wrong code.

The prompts below are designed around a practical agent workflow:

1. Prime the agent on the authoritative docs
2. Inspect the actual MODFLOW workspace before writing code
3. Generate code or configuration with explicit guardrails
4. Review the result against the docs before trusting it
5. Troubleshoot with doc-backed checks when trajectories look wrong

These prompts assume the agent can read URLs or local copies of the
documentation. If it cannot access a source, it should say which source is
missing and stop rather than guess. If the agent cannot browse URLs at all,
paste the content of `llms.txt` (or `llms-full.txt` for deeper context)
directly into the chat as a substitute.

---

## Recommended Sources

These are the highest-value references to name explicitly in your prompt:

- `https://sspa-inc.github.io/mp3du-rs-docs/llms.txt` - compact LLM primer
- `https://sspa-inc.github.io/mp3du-rs-docs/llms-full.txt` - full machine-readable reference
- `https://sspa-inc.github.io/mp3du-rs-docs/getting-started/quickstart/` - first end-to-end example
- `https://sspa-inc.github.io/mp3du-rs-docs/reference/units-and-conventions/` - sign conventions, `water_table`, indexing, CSR layout
- `https://sspa-inc.github.io/mp3du-rs-docs/reference/iface-flow-routing/` - IFACE bucket routing and `q_vert` rules
- `https://sspa-inc.github.io/mp3du-rs-docs/guides/building-configs/` - `SimulationConfig` patterns
- `https://sspa-inc.github.io/mp3du-rs-docs/guides/troubleshooting/` - common capture and hydration problems

---

## 1. Fast Priming Prompt

*Use this at the start of a new chat. It is short enough for quickstart use, but still forces the agent onto the published mp3du conventions before code generation.*

**Recommended role:** expert hydrogeologist, scientific Python developer, and conservative API integrator.

**Prompt:**

> Act as an expert hydrogeologist and scientific Python developer specializing in MODFLOW and groundwater particle tracking.
>
> I am working with the `mp3du` Python library. Treat the published `mp3du` documentation as authoritative, and do not invent undocumented APIs or fall back to older MODPATH conventions.
>
> Before writing any code, read these sources:
> - `https://sspa-inc.github.io/mp3du-rs-docs/llms.txt`
> - `https://sspa-inc.github.io/mp3du-rs-docs/getting-started/quickstart/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/units-and-conventions/`
>
> If you cannot access any of them, tell me which source is unavailable and stop instead of guessing.
>
> Then reply with:
> 1. A 4-bullet list of non-negotiable implementation rules covering `water_table`, `face_flow`, `q_well`, and IFACE / `q_vert` handling.
> 2. A short list of the docs you will consult again before writing code.

---

## 2. The Model Intake Prompt

*Use this before asking the agent to write code. It forces the agent to inspect your actual MODFLOW workspace and identify what is known, unknown, and potentially ambiguous.*

**Recommended role:** project intake analyst and implementation planner.

**Prompt:**

> Act as an expert hydrogeologist and scientific Python developer specializing in MODFLOW, `flopy`, and `mp3du`.
>
> First, read these sources:
> - `https://sspa-inc.github.io/mp3du-rs-docs/llms.txt`
> - `https://sspa-inc.github.io/mp3du-rs-docs/getting-started/quickstart/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/units-and-conventions/`
>
> Then inspect my model folder and tell me what kind of MODFLOW model I appear to have, which files matter for `mp3du`, and which required arrays can be extracted directly versus which ones still need to be derived.
>
> Do not write the final script yet. Return exactly these sections:
> 1. `Observed model files`
> 2. `Likely model flavor and packages`
> 3. `Arrays needed for mp3du`
> 4. `Known risks or missing information`
> 5. `Recommended next prompt`
>
> In your intake, explicitly mention:
> - where layer type will come from (`LAYTYP`, `LAYCON`, or `icelltype`)
> - how face connectivity / CSR arrays are expected to be assembled
> - whether IFACE boundary metadata appears available
> - whether the model likely needs separate cell-to-cell `q_vert` versus total `q_top` / `q_bot` arrays

---

## 3. The End-to-End Starter Script Prompt

*Use this when you want a full Python script that loads a MODFLOW model, hydrates mp3du inputs, fits Waterloo, runs one or more particles, and plots the result.*

**Recommended role:** implementation partner with strict doc compliance.

**Prompt:**

> Act as an expert hydrogeologist and scientific Python developer specializing in MODFLOW, `flopy`, and groundwater particle tracking.
>
> Before writing code, read these sources:
> - `https://sspa-inc.github.io/mp3du-rs-docs/llms-full.txt`
> - `https://sspa-inc.github.io/mp3du-rs-docs/getting-started/quickstart/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/units-and-conventions/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/iface-flow-routing/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/guides/building-configs/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/guides/troubleshooting/`
>
> I have a folder containing a completed MODFLOW model. Write a complete Python script that:
> 1. Uses `flopy` to load the model.
> 2. Extracts or derives the arrays needed for `mp3du`, including `top`, `bot`, `porosity`, `head`, `face_flow`, `q_well`, and the grid geometry.
> 3. Constructs `water_table` from the model layer type rules.
> 4. Hydrates `CellProperties`, `CellFlows`, and `WaterlooInputs`.
> 5. Fits the Waterloo velocity field.
> 6. Builds a valid `SimulationConfig`, tracks at least one particle, and plots the trajectory with `matplotlib`.
>
> Non-negotiable implementation rules:
> - Use `import mp3du` as the canonical import.
> - Build the configuration via `mp3du.SimulationConfig.from_json(json.dumps(config_dict))` and call `config.validate()`.
> - Construct `water_table` from layer type as follows: confined `0 -> top`, unconfined `1 -> head`, convertible `> 0 -> min(head, top)`.
> - Pass raw MODFLOW `face_flow` to `hydrate_cell_flows()`.
> - Pass negated `face_flow` to `hydrate_waterloo_inputs()`.
> - Pass direct per-cell `q_well` arrays in raw MODFLOW sign to both hydration functions.
> - If you are starting from IFACE-tagged `bc_flow` records, keep `bc_flow` in raw MODFLOW sign and use the documented IFACE routing rules, or `route_iface_bc_flows()`, to build per-cell `q_well`, `q_other`, `q_top`, and `q_bot` contributions.
> - Keep `q_vert` as cell-to-cell vertical flow only; do not add IFACE 5, 6, or 7 boundary contributions to `q_vert`.
> - If boundary capture data exists, pass the `bc_*` arrays to `hydrate_cell_flows()` instead of using `has_well=True` as a workaround for non-well boundaries.
> - Do not invent support for IFACE 1, 3, or 4.
> - If a required array or package cannot be determined from the files, leave an explicit TODO and explain the blocker instead of guessing.
>
> Return:
> 1. The script
> 2. A short `Assumptions / TODOs` section
> 3. A short `Validation checklist` with the first doc-backed checks I should run

---

## 4. The Data Hydration Builder Prompt

*Use this when you already have extracted arrays and only need the tricky hydration code for `mp3du`.*

**Recommended role:** numerical data-loading specialist.

**Prompt:**

> I already have extracted MODFLOW arrays such as `top`, `bot`, `porosity`, `head`, `face_flow`, and `q_well`, and I need Python code that prepares valid inputs for `mp3du.hydrate_cell_properties()`, `mp3du.hydrate_cell_flows()`, and `mp3du.hydrate_waterloo_inputs()`.
>
> Before writing code, read:
> - `https://sspa-inc.github.io/mp3du-rs-docs/llms-full.txt`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/units-and-conventions/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/iface-flow-routing/`
>
> Write Python helper code that does all of the following:
> 1. Builds `water_table` correctly from layer type.
> 2. Prepares per-cell arrays for `hydrate_cell_properties()`.
> 3. Prepares `CellFlows` arrays using raw MODFLOW signs where required.
> 4. Prepares `WaterlooInputs` arrays using Waterloo sign conventions where required.
> 5. Keeps `q_vert` as cell-to-cell vertical flow only, while `q_top` and `q_bot` can carry total vertical flow for `hydrate_cell_flows()`.
> 6. If IFACE-tagged boundary records are present, keeps `bc_flow` in raw MODFLOW sign and routes them to the correct buckets without double counting.
>
> Please include:
> - the exact `water_table` loop or vectorized equivalent
> - short assertions for array length, finiteness, `top > bot`, and CSR validity
> - no invented placeholder values unless they are clearly labeled as placeholders

---

## 5. The Configuration Builder Prompt

*Use this when you want the agent to generate a valid `SimulationConfig` dictionary or JSON block for a specific physical scenario.*

**Recommended role:** schema-aware configuration author.

**Prompt:**

> Before generating a configuration, read:
> - `https://sspa-inc.github.io/mp3du-rs-docs/llms-full.txt`
> - `https://sspa-inc.github.io/mp3du-rs-docs/guides/building-configs/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/schema-reference/`
>
> Using those docs as the source of truth, generate a complete Python dictionary for `SimulationConfig` for this scenario:
> - [describe your physical scenario here]
>
> Requirements:
> - Use only documented schema fields.
> - Set `velocity_method` to `Waterloo`.
> - Use a documented solver.
> - Use `direction` as either `1.0` or `-1.0` only.
> - Include every required block: `adaptive`, `dispersion`, `capture`, and the top-level timing fields.
> - If you omit `capture_radius` or `face_epsilon`, say why.
>
> Return exactly two sections:
> 1. `config_dict = {...}`
> 2. `Validation notes`

---

## 6. The Review Prompt

*Use this after the agent writes code. It turns the agent into a skeptical reviewer that checks the generated script against the docs instead of just defending its own output.*

**Recommended role:** reviewer focused on behavioral correctness.

**Prompt:**

> Act as a skeptical reviewer of `mp3du` integration code.
>
> Before reviewing, read:
> - `https://sspa-inc.github.io/mp3du-rs-docs/llms-full.txt`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/units-and-conventions/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/iface-flow-routing/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/guides/building-configs/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/guides/troubleshooting/`
>
> Review my script or notebook against the published docs. Focus on bugs, physics mismatches, or behavior-changing mistakes, not style.
>
> Specifically check for:
> - incorrect `water_table` construction
> - incorrect `face_flow` sign handling
> - incorrect `q_well` handling
> - accidental double counting or misuse of `q_vert`, `q_top`, or `q_bot`
> - unsupported or wrong IFACE handling
> - misuse of `has_well` for non-well boundaries
> - invalid `SimulationConfig` fields or enums
> - wrong indexing assumptions or broken CSR arrays
>
> Return findings ordered by severity. If you find no issues, say that explicitly and list residual risks or missing validation steps.

---

## 7. The Troubleshooting Prompt

*Use this when the code runs but the behavior looks wrong: particles move too fast, fail to capture, stick to faces, or terminate with an unexpected status.*

**Recommended role:** diagnostics engineer for groundwater particle tracking.

**Prompt:**

> My `mp3du` setup runs, but the trajectories or capture behavior look wrong.
>
> Before answering, read:
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/units-and-conventions/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/reference/iface-flow-routing/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/guides/troubleshooting/`
> - `https://sspa-inc.github.io/mp3du-rs-docs/getting-started/quickstart/`
>
> Based on those docs, give me the top 5 hypotheses to check first. For each hypothesis, include:
> 1. why it matches the symptoms
> 2. the exact arrays, config fields, or signs I should inspect
> 3. what result would confirm or rule it out
>
> In your ranked list, explicitly consider:
> - `water_table` too small in confined layers
> - `face_flow` sign mismatch between `hydrate_cell_flows()` and `hydrate_waterloo_inputs()`
> - `q_well` sign mismatch
> - IFACE 5, 6, or 7 flows being incorrectly included in `q_vert`
> - missing or wrong `bc_*` arrays
> - misuse of `has_well` or `is_domain_boundary`
> - capture settings such as `capture_radius` or `face_epsilon`
