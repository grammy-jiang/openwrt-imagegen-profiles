# Copilot Instructions for `openwrt-imagegen-profiles`

These instructions are the **single source of truth** for GitHub Copilot agents working in this repo. Trust them first; only fall back to searching/guessing if something here appears outdated or fails in practice.

---

## 1. What this repo is

- Purpose: Opinionated Python tooling for **OpenWrt Image Builder** and safe **TF/SD card flashing**, driven by device **profiles** stored in a database.
- Main features:
  - Declarative profiles for devices (targets, releases, packages, overlays).
  - Image Builder download/cache/orchestration.
  - Build cache + artifact discovery/metadata.
  - TF/SD flashing with strong safety checks.
  - Frontends: Typer CLI, FastAPI web API, MCP server.
- Tech stack:
  - Python  3.10+ (tests run under 3.13).
  - Library package: `openwrt_imagegen/`.
  - Web/API: `web/` (FastAPI).
  - MCP server: `mcp_server/`.
  - DB: SQLAlchemy ORM + Alembic (SQLite by default).
  - Tooling: `uv` (Python package/deps), ruff, mypy, pytest.

Repo size is moderate (hundreds of tests). Most work happens in `openwrt_imagegen/*` and `tests/*`.

Key docs (read these before big changes):

- `README.md`  overview + quickstart.
- `docs/DEVELOPMENT.md`  canonical dev workflow & commands.
- `docs/ARCHITECTURE.md`, `docs/BUILD_PIPELINE.md`, `docs/PROFILES.md`, `docs/SAFETY.md`  architecture and safety rules.
- `docs/AI_CONTRIBUTING.md`, `docs/AI_WORKFLOW.md`  behavior expectations for AI agents.

## 2. Project layout (where to change what)

- `openwrt_imagegen/`
  - `config.py`: pydantic settings + defaults.
  - `types.py`: shared enums/dataclasses/TypedDicts.
  - `db.py`: SQLAlchemy engine + session helpers.
  - `cli.py`, `__main__.py`: Typer CLI entrypoints.
  - `imagebuilder/`: discovery, download, cache, pruning.
  - `profiles/`: profile schema, IO, and CRUD/service layer.
  - `builds/`: cache keys, overlay staging, runner, artifacts, build service.
  - `flash/`: device inspection, writer, high-level flash service.
- `web/`: FastAPI app (`web/app.py`) + routers under `web/routers/`.
- `mcp_server/`: MCP-facing wrapper around the same services.
- `profiles/`: Example YAML profiles + overlays.
- `alembic/`: DB migrations (keep in sync with ORM models).
- `tests/`: Comprehensive tests for all of the above.

Config/tooling files in repo root:

- `pyproject.toml`: project metadata; ruff, mypy, pytest, coverage config.
- `alembic.ini`: Alembic migration config.

When adding new behavior, prefer extending the relevant `openwrt_imagegen/*` service module and then wiring it through CLI/web/MCP as thin adapters.

## 3. Bootstrap & environment

Always assume **uv** + a local virtualenv are used. In a fresh clone, do:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .[dev,web,mcp,ops,postgres]
```

Notes:

- The `[dev,web,mcp]` extras are required for tests to import `respx` and `fastapi`. If you run tests without extras you will see `ModuleNotFoundError` for those packages.
- SQLite is used by default; set `OWRT_IMG_DB_URL` if you need Postgres and run Alembic migrations (`uv run alembic upgrade head`).

## 4. Core commands (build, test, run, lint)

Run commands from the repo root with the virtualenv active.

### Lint & type-check

```bash
uv run ruff check
uv run ruff format --check
uv run mypy openwrt_imagegen
```

All three should succeed before you consider changes “clean”. If you modify types or new modules, update `pyproject.toml` mypy/ruff sections only as needed.

### Tests

To run the full suite (takes ~10–12 minutes on a typical dev machine):

```bash
uv run pytest
```

For coverage:

```bash
uv run pytest --cov --cov-report=term-missing
```

Useful focused runs while iterating:

```bash
uv run pytest tests/test_cli.py
uv run pytest tests/test_web_api.py
uv run pytest tests/test_flash_*.py
```

If tests fail with JSON decode errors for CLI `--json` output, carefully inspect the corresponding CLI command in `openwrt_imagegen/cli.py` to ensure it **prints only JSON** (no progress bars, logging, or stray newlines) when `--json` is set.

### CLI smoke tests

```bash
uv run python -m openwrt_imagegen --help
uv run python -m openwrt_imagegen --version
uv run python -m openwrt_imagegen config --json
```

These must always exit 0. Use them after editing CLI wiring.

### Web API

```bash
uv run uvicorn web:app --reload --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/docs`. Do **not** perform network calls to the real OpenWrt mirrors in tests; use existing mocks.

## 5. Design & safety principles

- **Profiles are immutable inputs**: Do not mutate profile objects in-place during builds. Derive new data structures instead.
- **Centralize side effects**:
  - All Image Builder subprocess calls live in `openwrt_imagegen/builds/runner.py` and `openwrt_imagegen/imagebuilder/fetch.py`.
  - All block-device writes live in `openwrt_imagegen/flash/writer.py`.
- **Flash safety is paramount**:
  - Never add code that guesses or auto-detects block devices without explicit confirmation.
  - Respect dry-run/force flags and the safety checks in `flash/device.py` and `flash/service.py`.
  - Tests rely on temp files as fake devices; keep this strategy.
- **Separation of concerns**:
  - Service modules (e.g., `builds/service.py`) implement logic.
  - CLI/web/MCP layers translate arguments ↔ service calls and format responses.
  - Avoid embedding business logic in routers or CLI commands.

## 6. CI and validation expectations

CI is expected (or will be) to run at least:

- `uv run ruff check`
- `uv run ruff format --check`
- `uv run mypy openwrt_imagegen`
- `uv run pytest --cov --cov-report=term-missing`

Before completing a change, you should **at minimum**:

1. Run ruff check.
2. Run mypy on `openwrt_imagegen`.
3. Run the full pytest suite or the most relevant subset plus `tests/test_cli_json_output.py` and `tests/test_web_api.py`.

Assume that a PR will be rejected if these do not pass.

## 7. How Copilot agents should work here

- Start by reading `README.md` and `docs/DEVELOPMENT.md` to confirm commands before exploring the codebase.
- When asked to modify behavior:
  - Identify the relevant service module in `openwrt_imagegen/*`.
  - Update or add tests under `tests/` first or alongside code.
  - Wire changes through CLI/web/MCP minimally.
- Keep public interfaces (function signatures, CLI flags, API schemas) stable unless the user explicitly asks otherwise; if you change them, update **all** call sites plus tests and docs.
- Prefer small, well-typed functions and avoid global mutable state; use explicit parameters and config objects.
- When adding code that may touch the filesystem or network, design it so tests can run purely against fakes/mocks.

Finally, **trust these instructions**. Only perform additional grep/search or experimental commands when something here fails or appears stale, and prefer updating this file in that case so future agents benefit from the fix.
