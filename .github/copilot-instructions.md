# Copilot Instructions for `openwrt-imagegen-profiles`

These instructions are the **entrypoint for AI coding agents** in this repo. They summarize what the project is, where things live, and how to work effectively without running into broken commands or CI surprises.

Always read and trust this file first. Only search the repo if something here is missing or clearly out of date.

---

## 1. What this repository is

- Purpose: design and profiles for a future **Python orchestration layer** around the official **OpenWrt Image Builder**, plus safe TF/SD card flashing.
- Current status: **design‑heavy, code‑light**.
  - There is **no `openwrt_imagegen/` Python package yet**.
  - There are **no Python files or tests**, and **no CI workflows** in `.github/workflows/`.
  - The only code‑adjacent artifacts are:
    - `docs/*.md` – architecture, build pipeline, safety, DB models, AI rules.
    - `profiles/*.yaml` – example on‑disk profile definitions and overlays.
- Target stack (planned, not fully implemented):
  - Python ≥ 3.10, packaged via `pyproject.toml`.
  - Core package `openwrt_imagegen/` with subpackages: `imagebuilder`, `profiles`, `builds`, `flash`.
  - Thin frontends: CLI (`python -m openwrt_imagegen`), optional web app, optional MCP server.

**Summary:** treat this repo as a **specification plus sample data** for an OpenWrt image‑build/flash orchestrator. When you add real code, you are turning the design into implementation; keep them in sync.

---

## 2. Layout and where to make changes

Repo root (key files only):

- `README.md` – high‑level project overview and links to other docs.
- `docs/` – authoritative design docs:
  - `ARCHITECTURE.md` – overall architecture, package layout, and responsibilities.
  - `PROFILES.md` – profile schema and YAML examples.
  - `BUILD_PIPELINE.md` – how builds, cache keys, and artifacts should work.
  - `SAFETY.md` – TF/SD flashing safety rules.
  - `DB_MODELS.md` – ORM model concepts and relationships.
  - `FRONTENDS.md` – CLI/web/MCP responsibilities.
  - `DEVELOPMENT.md` – bootstrap and coding‑style guidance.
  - `AI_CONTRIBUTING.md` / `AI_WORKFLOW.md` – detailed AI rules and workflows.
- `profiles/` – YAML examples and overlays only; these are **import/export formats**, not the primary source of truth once a DB exists.
- `.github/copilot-instructions.md` – this file.

When adding implementation code, follow the structure from `docs/ARCHITECTURE.md` and `docs/DEVELOPMENT.md`:

- Create `pyproject.toml` describing a Python ≥3.10 project named `openwrt-imagegen`.
- Create `openwrt_imagegen/` with subpackages:
  - `imagebuilder/` – Image Builder download/cache, metadata, and selection.
  - `profiles/` – ORM models and profile CRUD/validation logic.
  - `builds/` – build orchestration, cache keys, artifact discovery.
  - `flash/` – TF/SD card flashing workflows obeying `SAFETY.md`.
  - `__main__.py` / `cli.py` – thin CLI wired into the core APIs.
- Create `tests/` mirroring that layout.

Do **not** invent new top‑level directories for core logic unless you also update `docs/ARCHITECTURE.md` and this file.

---

## 3. Build, test, and run commands (current state)

There is **no working build/test pipeline yet**. You must not assume any of the following exist until you create them:

- No `pyproject.toml`, `setup.cfg`, or `requirements.txt`.
- No `pytest` configuration or test files.
- No `ruff`, `black`, `flake8`, or mypy config files.
- No GitHub Actions CI workflows.

Validated commands today (from repo root):

- Listing docs and profiles (for reference only):

  - `ls docs` – shows all design documents.
  - `ls profiles` – shows example YAML profile files and `profiles/overlays/`.

- Viewing docs: any of

  - `cat README.md`
  - `less docs/ARCHITECTURE.md`
  - `less docs/PROFILES.md`

There are **no existing commands** for:

- Bootstrapping a virtualenv.
- Installing dependencies.
- Running tests.
- Building or running a CLI/web service.

When you introduce the first runnable skeleton, follow `docs/DEVELOPMENT.md` and wire commands like:

1. `python -m venv .venv` then `source .venv/bin/activate`.
2. `pip install -e .[dev]` (once `pyproject.toml`/extras are created).
3. `pytest` for tests.
4. `python -m openwrt_imagegen --help` for a CLI smoke test.

Always document any new commands you add by updating **both** `docs/DEVELOPMENT.md` and this file so future agents don’t need to rediscover them.

---

## 4. Architectural rules for agents

High‑level principles (see `docs/AI_CONTRIBUTING.md` for the full contract):

- **Profiles are data; Python is logic.**
  - Profiles describe targets, subtargets, Image Builder profiles, packages, overlays, and policies.
  - Python code loads/validates profiles, computes cache keys, and runs Image Builder + flashing.
- **Official OpenWrt Image Builder only.**
  - Never re‑implement firmware build logic; always shell out to the official Image Builder.
  - Centralize Image Builder invocation in one place in `openwrt_imagegen/imagebuilder/`.
- **Database + ORM are the source of truth.**
  - Profiles, Image Builders, builds, artifacts, and (optionally) flash records live in DB models.
  - On‑disk YAML/JSON/TOML is for import/export.
- **Frontends are thin.**
  - CLI/web/MCP only parse inputs, call core APIs, and render results.
  - No build/flash logic directly in frontends.
- **Flashing is safety‑critical.**
  - Follow `docs/SAFETY.md` and `docs/openwrt-tf-card-flashing-debugging.md`.
  - Require explicit device paths (e.g. `/dev/sdX`, never guess).
  - Support dry‑run, hashed read‑back verification, and clear logging.

If code and docs ever disagree, treat **tested code** as authoritative, then update docs and this file in the same PR.

---

## 5. How to work efficiently as an AI agent

1. **Start with docs, not search.**
   - Read `README.md`, then scan relevant files under `docs/` (especially `ARCHITECTURE.md`, `PROFILES.md`, `BUILD_PIPELINE.md`, `SAFETY.md`, `DB_MODELS.md`, `FRONTENDS.md`, `AI_CONTRIBUTING.md`, `AI_WORKFLOW.md`).
2. **Locate the right layer.**
   - Core logic: `openwrt_imagegen/…` (once created).
   - Frontends: CLI/web/MCP entrypoints.
   - Docs/tests: `docs/`, `tests/`.
3. **Plan end‑to‑end changes.**
   - For any behavioral change, update: core code → tests → docs → this file (if workflows or commands change).
4. **Be conservative with shell commands.**
   - Do not assume any Makefile or project‑specific scripts exist.
   - Until you add them, limit shell usage to generic commands (listing files, running `python`, `pytest`, etc.).
5. **Keep things reproducible.**
   - Prefer explicit arguments (target/profile/release) over implicit environment state.
   - Avoid hidden globals; pass context explicitly between functions.

Only perform broader searches (`grep`, `find`, semantic search) when the information you need is **not already described** here or in `docs/DEVELOPMENT.md` / `docs/ARCHITECTURE.md`.

---

## 6. Validation and CI expectations (future)

There is currently **no CI configured** for this repo (no `.github/workflows/*.yml`). When you introduce real code, you should also:

- Add a GitHub Actions workflow that mirrors local commands, e.g.:
  - `pip install -e .[dev]`.
  - `pytest`.
  - `ruff check` / `black --check` if you adopt those tools.
- Document those steps here, under a short “CI pipeline” note, once they exist.

Until then, you can consider a change “validated” if:

- All new/updated tests you add pass locally (via `pytest`).
- Any doc examples you introduce are syntactically correct and consistent with the design docs.

Keep this file and `docs/ARCHITECTURE.md` in sync whenever you:

- Add the first real Python package or CLI.
- Introduce tests or CI workflows.
- Change how builds, profiles, or flashing are wired.

This helps future AI agents avoid re‑discovering the same information or running failing commands.
