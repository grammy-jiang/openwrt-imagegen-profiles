# Copilot Instructions for `openwrt-imagegen-profiles`

These instructions guide AI coding agents working in this repository. Treat this file as the first stop before exploring; only search the codebase when something here is missing or clearly wrong.

This repo is currently mostly **design + profile data**; the core Python package is planned but not yet checked in. That means most "build" and "test" commands do not exist yet – document drafts describe the future system.

---

## 1. High-level repo overview

- Purpose: opinionated tooling around the official **OpenWrt Image Builder** to manage:
  - Declarative **device profiles** (targets, subtargets, Image Builder profile names, releases, packages, overlays).
  - A Python orchestration layer that downloads/caches Image Builders, runs reproducible builds, tracks artifacts in a DB, and safely flashes TF/SD cards.
  - Multiple frontends (CLI, web UI, MCP server) over the same Python core.
- Current contents:
  - Top-level design docs: `README.md`, `ARCHITECTURE.md`, `BUILD_PIPELINE.md`, `DB_MODELS.md`, `FRONTENDS.md`, `SAFETY.md`, `PROFILES.md`, `AI_CONTRIBUTING.md`, `AI_WORKFLOW.md`.
  - Example profile YAMLs under `profiles/*.yaml` and overlay dirs under `profiles/overlays/`.
  - No `openwrt_imagegen/` package, no tests, and no CI workflows are present yet.
- Languages / runtimes (intended): Python 3.10+ for orchestration; OpenWrt Image Builder (external tool) for firmware builds; optional web/MCP services layered on top.

Always read `README.md` and `ARCHITECTURE.md` before implementing new behavior; they define what the eventual code must do.

---

## 2. Project layout & where to put code

Planned structure (some directories do not exist yet):

- `profiles/`
  - YAML examples of device profiles (see `PROFILES.md` for schema).
  - `profiles/overlays/` holds filesystem overlays used by some example profiles.
- `openwrt_imagegen/` (planned)
  - Core Python package for Image Builder management, profiles, builds, flashing.
  - When adding new code, create this package and submodules following `ARCHITECTURE.md` and `BUILD_PIPELINE.md`:
    - `openwrt_imagegen/imagebuilder/` – download/cache official Image Builder archives; DB metadata.
    - `openwrt_imagegen/profiles/` – ORM models + profile validation and management.
    - `openwrt_imagegen/builds/` – build orchestration, cache key computation, build records & artifacts.
    - `openwrt_imagegen/flash/` – TF/SD card flashing workflows honoring `SAFETY.md`.
    - `openwrt_imagegen/cli.py` or `openwrt_imagegen/__main__.py` – thin CLI.
- `web/` (planned) – web UI as a thin layer over `openwrt_imagegen`.
- `mcp_server/` (planned) – MCP server calling the same core APIs.
- `tests/` (planned) – unit/integration tests mirroring the package layout (use pytest-style tests).

When introducing new modules, update the relevant design docs to match reality instead of diverging from them.

---

## 3. Build, test, and runtime commands

### 3.1 Current state

- There is **no** `pyproject.toml`, `requirements.txt`, or `setup.cfg` yet.
- There are **no** `tests/` or test runners defined.
- There are **no** GitHub Actions workflows or other CI configs checked in.
- There is **no** implemented CLI entry point.

So, at the moment:

- You cannot run a real build pipeline from this repo alone.
- You cannot run automated tests.
- Any `pytest`, `python -m openwrt_imagegen`, or similar command will fail until you create the corresponding package/files.

### 3.2 Recommended initial bootstrap (for the first implementation)

When you add real code, follow this order to minimize command failures:

1. **Create the package skeleton**
   - Add `openwrt_imagegen/__init__.py` and the planned subpackages (`imagebuilder`, `profiles`, `builds`, `flash`).
   - Add a simple `pyproject.toml` (PEP 621) or `requirements.txt` that at least pins Python 3.10+ and core deps (ORM, HTTP client, CLI framework) as needed.
2. **Add a minimal CLI**
   - Implement `python -m openwrt_imagegen` or a small `cli.py` using `argparse`/Typer/Click.
   - Provide at least a `--help` command that works without talking to OpenWrt or the database.
3. **Add tests**
   - Create `tests/` and basic pytest configuration.
   - Ensure `pytest` runs even if many tests are `xfail` or skipped initially.
4. **Wire in real build logic**
   - Implement the logic described in `BUILD_PIPELINE.md` and `ARCHITECTURE.md`.
   - Add tests for cache key computation, profile validation, and basic build orchestration (with mocks/fakes, not real Image Builder or TF cards).

Once this scaffolding exists, document concrete commands here (e.g. `python -m openwrt_imagegen ...`, `pytest`) and keep them up to date. Until then, avoid guessing commands in automation.

---

## 4. Behavioral rules for AI changes

- **Profiles are immutable inputs**
  - Do not mutate profile objects during a build; derive new structures instead.
  - Always treat a profile as a snapshot that deterministically yields the same build outputs.
- **OpenWrt Image Builder is the only build engine**
  - Never reimplement firmware/package logic; always shell out to the official Image Builder.
  - Centralize command construction in one module so flags and environment are easy to audit and test.
- **Separation of concerns**
  - Keep parsing/validation of profile data separate from the code that actually runs Image Builder.
  - TF/SD card flashing logic must live in its own module and never be "hidden" inside build steps.
- **Safety over convenience for flashing** (see `SAFETY.md`)
  - Require explicit block device paths (e.g. `/dev/sdX`, never guess).
  - Prefer dry-run and clear logging.
  - Use hash-based read-back verification to detect ghost writes and bad cards.
- **Database + ORM as source of truth** (see `DB_MODELS.md`)
  - Profiles, Image Builders, builds, artifacts, and (optionally) flash records should be modeled and persisted via an ORM.
  - YAML profile files in `profiles/` are examples/import-export formats, not the primary store.
- **Frontends are thin** (see `FRONTENDS.md`)
  - CLI, web UI, and MCP server must call into shared Python functions and avoid duplicating business logic.

Always cross-check behavior against `ARCHITECTURE.md`, `BUILD_PIPELINE.md`, and `AI_CONTRIBUTING.md` before making significant changes.

---

## 5. Validation and CI expectations

Because there is no CI yet, it is your responsibility to set up local validation when you introduce code:

- Add a consistent test entry point (prefer `pytest`).
- Add a simple linting step (e.g. `ruff` or `flake8`) once the package exists.
- When CI workflows are added under `.github/workflows/`, mirror their steps locally and update this file to describe the exact command sequence.

Until CI exists, human reviewers will rely on:

- Passing local tests.
- Clear adherence to the documented architecture and safety rules.
- Sensible dependency and environment choices (Python 3.10+, standard tooling).

---

## 6. How to use these instructions

- Treat this file, `AI_CONTRIBUTING.md`, `AI_WORKFLOW.md`, and `ARCHITECTURE.md` as the **authoritative guidance** for AI work.
- **Trust these instructions first**; only reach for grep, tree listing, or exploratory commands when:
  - You need to inspect a specific doc (e.g. `PROFILES.md` for schema details), or
  - You suspect these instructions are out of date or incomplete.
- When you discover that reality diverges from this file (for example, once a `pyproject.toml` or CI workflows are added), **update this file in the same PR** so future agents have accurate, low-friction guidance.

Goal: minimize trial-and-error shell commands and codebase spelunking by keeping this document tightly aligned with how the repository actually works.
