# Copilot Instructions for `openwrt-imagegen-profiles`

These instructions guide AI coding agents working in this repository. Focus on repeatable OpenWrt Image Builder workflows and Python tooling around them.

## 1. Big-picture architecture

- This repo is about **declarative device profiles** + **Python orchestration** around the official **OpenWrt Image Builder**, _not_ a generic OpenWrt SDK.
- Treat **profiles as data, Python as logic**:
  - Profiles encode targets, subtargets, Image Builder profile names, releases, packages, and optional overlays.
  - Python code is responsible for reading profiles, composing Image Builder CLI invocations, collecting artifacts, and logging.
- Expect a future split between:
  - A **Python CLI layer** (for local/CI usage).
  - An optional **service/MCP layer** that calls the same Python functions without duplicating business logic.

When in doubt, keep build/flash behavior in reusable Python modules and let CLIs/services be thin wrappers.

## 2. Conventions and design principles

- **Reproducibility first**
  - Prefer explicit parameters (target, profile, release, packages) over implicit defaults or environment-dependent behavior.
  - Avoid hidden state such as global config files or "current device" globals; pass explicit context objects or arguments.
- **Profiles are immutable inputs**
  - Do not mutate loaded profile objects in-place while building; derive new structures instead.
  - Treat a profile as a snapshot that should deterministically yield the same build outputs.
- **Separation of concerns**
  - Parsing/validating profile data is separate from executing Image Builder commands.
  - TF card flashing logic is separate from build logic but can share common types (e.g., image metadata, device identifiers).
- **Safety over convenience**
  - Any code that touches block devices (TF cards, disks) must:
    - Require explicit device paths.
    - Prefer dry-run and confirmation modes.
    - Log what will be done before doing it.

## 3. Project layout expectations

Even if some modules are not created yet, follow these patterns:

- `profiles/` (or similar future dir):
  - Data-only definitions for devices (YAML/JSON/TOML).
  - Keep schemas consistent; add validation helpers when patterns emerge.
- `imagegen/` or `openwrt_imagegen/` (Python package):
  - Core orchestration code for:
    - Loading/validating profiles.
    - Constructing Image Builder commands.
    - Running builds and collecting artifacts/logs.
- `cli.py` or `__main__.py`:
  - Thin argparse/Typer/Click wrapper around the orchestration library.

If you introduce new modules, align them with this separation and keep UX-focused code (argument parsing, prompts) out of the core.

## 4. External tools and integration points

- **OpenWrt Image Builder** is the authoritative build engine:
  - Never reimplement package selection or firmware construction logic; always shell out to the official tool.
  - Centralize command construction in one place so changes to Image Builder flags are easy to maintain.
- **CI / automation**
  - Design functions so they can be called non-interactively (no prompts, deterministic exits).
  - Prefer explicit output directories and log paths that CI can collect as artifacts.
- **Future MCP/service wrappers**
  - Expose idempotent, side-effect-controlled functions (e.g., `build_image(profile, options)`, `flash_tf_card(image, device)`).
  - Ensure return types include enough metadata (paths, checksums, logs) for higher layers to reason about state.

## 5. Developer workflows (expected)

When adding scripts or docs, align with these workflows:

- **Build**
  - Input: device profile ID or file path.
  - Steps: load profile → validate → ensure Image Builder present → run build → collect images + logs into a predictable output tree (e.g., `builds/<device>/<release>/...`).
- **Flash TF card (planned)**
  - Input: built image + explicit block device path.
  - Steps: verify image exists and matches device → optional dry-run/confirmation → write image → verify (e.g., checksum/read-back) → log operations.

Document any non-obvious environment variables or paths near where they are used.

## 6. Coding style and quality

- Use modern Python (3.10+) syntax and type hints where practical.
- Prefer small, testable functions with explicit parameters over large scripts.
- When adding new behaviors, add or update **self-checks or tests** alongside them (e.g., pytest-style tests or simple regression scripts in `tests/`).

## 7. How AI agents should work here

- Before generating new functionality, scan `README.md` and existing Python modules for how profiles and builds are modeled; copy existing patterns instead of inventing new ones.
- When unsure about a behavior (e.g., how to structure directories, how to name profiles), defer to clarity and reproducibility:
  - E.g., prefer `device_id/release/build-<timestamp>`-style paths to opaque hashes.
- Keep public interfaces stable: if you must change a function or CLI signature, update all call sites and, if present, docs/tests in the same change.

If anything in these instructions seems to conflict with the current code, follow the actual code and update this file to match reality rather than enforcing an outdated convention.
