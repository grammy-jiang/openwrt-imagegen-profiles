# Copilot Instructions for `openwrt-imagegen-profiles`

These instructions tell AI coding agents how to work efficiently in this repository. Treat this file as the **entrypoint**: trust it first, and only search the repo when something here is missing or clearly outdated.

## 1. What this repo is

- Purpose: opinionated orchestration around the official **OpenWrt Image Builder** for many devices, with profiles, builds, artifacts, and (eventually) TF/SD flashing managed by a shared Python library plus thin frontends.
- Current status (see `docs/DEVELOPMENT.md`): **package skeleton implemented**. There is:
  - `pyproject.toml` with Python ≥3.10 and dependency groups (core, dev, web, postgres, ops).
  - `openwrt_imagegen/` package with subpackages (`imagebuilder/`, `profiles/`, `builds/`, `flash/`) and shared modules (`types.py`, `config.py`, `cli.py`).
  - Tests in `tests/` with CLI smoke tests, config tests, and types tests.
  - A rich set of design docs under `docs/` and sample device profiles under `profiles/`.
- Tech stack:
  - Python ≥ 3.10, packaged via `pyproject.toml`.
  - CLI (Typer + Rich), optional FastAPI web app, optional MCP server.
  - ORM (SQLAlchemy + Alembic), Pydantic for models, HTTPX, Ruff/Mypy/Pytest for QA (see `docs/DEVELOPMENT.md`).

Always read `README.md`, `docs/ARCHITECTURE.md`, `docs/BUILD_PIPELINE.md`, `docs/PROFILES.md`, and `docs/AI_CONTRIBUTING.md` before implementing new behavior.

## 2. Project layout and where to put code

Repository is intentionally small:

- Root: `README.md`, `LICENSE`, `CODE_OF_CONDUCT.md`, `docs/`, `profiles/`, and `.github/`.
- `docs/`: authoritative design and workflow docs:
  - `ARCHITECTURE.md` – overall system, package layout, and frontends.
  - `BUILD_PIPELINE.md` – how profiles become Image Builder runs and artifacts.
  - `PROFILES.md` – profile schema and examples.
  - `DB_MODELS.md`, `FRONTENDS.md`, `OPERATIONS.md`, `SAFETY.md` – DB, CLI/web/MCP responsibilities, and operational/safety rules.
  - `DEVELOPMENT.md` – bootstrap and tooling plan (uv, tests, linting, CI outline).
  - `AI_CONTRIBUTING.md`, `AI_WORKFLOW.md` – mandatory rules + workflow for AI agents.
- `profiles/`: concrete device profile examples in YAML plus future overlay files in `profiles/overlays/`.
- `.github/`: this file (Copilot instructions). CI workflows are not present yet.

The package structure:

- `openwrt_imagegen/`: main Python package
  - `__init__.py`: package metadata and version
  - `types.py`: shared type definitions (enums, dataclasses, TypedDicts)
  - `config.py`: pydantic Settings for configuration
  - `db.py`: SQLAlchemy engine, session management, and Base model
  - `cli.py`: Typer-based CLI with subcommands
  - `__main__.py`: entry point for `python -m openwrt_imagegen`
  - `imagebuilder/models.py`: ImageBuilder ORM model
  - `profiles/models.py`: Profile ORM model
  - `builds/models.py`: BuildRecord and Artifact ORM models
  - `flash/models.py`: FlashRecord ORM model
  - `py.typed`: marker for typed package
- `web/`: FastAPI web application
  - `app.py`: FastAPI application factory
  - `deps.py`: Database dependency injection
  - `routers/`: API route handlers (health, config, profiles, builders, builds, flash)
- `mcp_server/`: MCP (Model Context Protocol) server for AI tools
  - `__init__.py`: Package marker, exports mcp server instance
  - `server.py`: FastMCP server setup with tool definitions
  - `errors.py`: Structured error types with stable codes
  - `schemas.py`: Pydantic response schemas for MCP tools
- `alembic/`: Database migration scripts
  - `env.py`: Alembic environment configuration
  - `versions/`: Migration files
- `tests/`: test files mirroring package structure

When adding real code, follow `docs/ARCHITECTURE.md` and `docs/AI_CONTRIBUTING.md`:

- Create `openwrt_imagegen/` at repo root with subpackages:
  - `imagebuilder/`, `profiles/`, `builds/`, `flash/`, shared `types.py`.
  - Keep OpenWrt‑specific orchestration and safety logic here.
- Add thin frontends:
  - CLI: `openwrt_imagegen/cli.py` or `__main__.py`.
  - Web app: `web/`.
  - MCP server: `mcp_server/`.
- Add `tests/` mirroring the package layout for unit/integration tests.

Do **not** introduce alternate core packages or top‑level folders for business logic without also updating `docs/ARCHITECTURE.md` and this file.

## 3. Build, test, and run commands

The Python package and tooling are now available. Use these commands:

1. Environment bootstrap

   - Create and activate a virtualenv, then install the project in editable mode:
     ```bash
     uv venv .venv
     source .venv/bin/activate
     uv pip install -e .[dev]
     ```
   - For full stack work (web/MCP/Postgres/ops), install extras:
     ```bash
     uv pip install -e .[dev,web,postgres,ops]
     ```

2. Linting and type checks

   - Run these commands:
     ```bash
     uv run ruff check
     uv run ruff format --check
     uv run mypy openwrt_imagegen
     ```

3. Tests and coverage

   - Tests live under `tests/` and are runnable with:
     ```bash
     uv run pytest
     uv run pytest --cov --cov-report=term-missing
     ```
   - Tests must not depend on real OpenWrt downloads or real block devices; use fakes/mocks and temp dirs.

4. Database migrations

   - Run Alembic migrations to create/update the database schema:
     ```bash
     uv run alembic upgrade head
     ```
   - Create a new migration after changing ORM models:
     ```bash
     uv run alembic revision --autogenerate -m "Description of changes"
     ```
   - Check current migration status:
     ```bash
     uv run alembic current
     ```

5. CLI smoke test

   - The minimal CLI works offline:
     ```bash
     uv run python -m openwrt_imagegen --help
     uv run python -m openwrt_imagegen --version
     uv run python -m openwrt_imagegen config --json
     ```
   - Profile management commands:
     ```bash
     uv run python -m openwrt_imagegen profiles --help
     uv run python -m openwrt_imagegen profiles validate profiles/home-ap-livingroom.yaml
     uv run python -m openwrt_imagegen profiles import profiles/
     uv run python -m openwrt_imagegen profiles list
     uv run python -m openwrt_imagegen profiles list --json
     uv run python -m openwrt_imagegen profiles list --target ath79 --release 23.05.2 --json
     uv run python -m openwrt_imagegen profiles show <profile-id>
     uv run python -m openwrt_imagegen profiles export /tmp/exports
     ```
   - Build and artifact commands:
     ```bash
     uv run python -m openwrt_imagegen build list --json
     uv run python -m openwrt_imagegen build batch --profile <profile-id> --json
     uv run python -m openwrt_imagegen artifacts list --json
     uv run python -m openwrt_imagegen artifacts list --build-id <build-id> --json
     uv run python -m openwrt_imagegen artifacts show <artifact-id> --json
     ```
   - Flash commands:
     ```bash
     uv run python -m openwrt_imagegen flash --help
     uv run python -m openwrt_imagegen flash image <image-path> <device> --dry-run --force --json
     uv run python -m openwrt_imagegen flash write <artifact-id> <device> --dry-run --force --json
     uv run python -m openwrt_imagegen flash list --json
     uv run python -m openwrt_imagegen flash list --status succeeded --json
     ```

6. Tox (optional, if introduced)
   - Mirror CI by running:
     ```bash
     uv run tox -e lint,type,test,coverage
     ```

Whenever you add or change any of these commands, update **both** `docs/DEVELOPMENT.md` and this file in the same PR.

## 4. Architectural rules for agents

- Treat **profiles as data, Python as logic**:
  - Profiles (YAML/DB) describe OpenWrt release/target/subtarget, profile name, packages, and overlays.
  - Python code loads/validates profiles, builds Image Builder commands, runs them, collects artifacts, and logs.
- Never re‑implement OpenWrt firmware logic; always shell out to the **official Image Builder** and centralize the command construction in one place.
- Keep frontends thin:
  - CLI/web/MCP must only parse inputs, call core APIs, and render outputs.
  - All build, cache, and flash orchestration lives under `openwrt_imagegen/`.
- Profiles and build inputs are **immutable** during a build; to change behavior, create a new profile or explicit options object.
- TF/SD flashing logic (once implemented) must follow the safety rules in `docs/SAFETY.md` and `docs/OPERATIONS.md`: explicit devices only, dry‑run support, flushed writes, hash‑based verification, and clear logging.

## 5. How to work as an AI agent

When you get a task in this repo:

1. Start by reading (in this order):
   - `.github/copilot-instructions.md` (this file).
   - `README.md`.
   - `docs/AI_CONTRIBUTING.md` and `docs/AI_WORKFLOW.md`.
   - Any design doc relevant to your change (`ARCHITECTURE.md`, `BUILD_PIPELINE.md`, `PROFILES.md`, etc.).
2. Prefer adding core library code + tests first; keep CLI/web/MCP changes as thin wiring.
3. When introducing new commands or behavior:
   - Make them non‑interactive by default and suitable for CI.
   - Add or update tests in `tests/`.
   - Document run/lint/test commands in `docs/DEVELOPMENT.md` and in this file.
4. Before proposing a change, locally run (once available): lint → type‑check → tests → CLI `--help` smoke. Do not assume CI will pass if these fail locally.
5. Treat this repo’s docs as **authoritative specs**. If code and docs disagree, align the code to the docs or update both together; never leave them inconsistent.

Only perform extra repo‑wide searches (grep, find, etc.) when something required for your task is not covered here or in the referenced docs, or when you suspect these instructions are stale.
