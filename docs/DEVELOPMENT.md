# Development Guide

This repository is currently design-heavy: the core Python package has not been implemented yet. Use this guide as the single place for day-to-day engineering info: bootstrap, style, configuration defaults, testing expectations, and working practices.

## 1) Status and layout
- Code status: design docs + profile examples only; no `openwrt_imagegen/` package or tests yet.
- Key design references: [README.md](../README.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PROFILES.md](PROFILES.md), [BUILD_PIPELINE.md](BUILD_PIPELINE.md), [SAFETY.md](SAFETY.md), [DB_MODELS.md](DB_MODELS.md), [FRONTENDS.md](FRONTENDS.md), [AI_CONTRIBUTING.md](AI_CONTRIBUTING.md), [AI_WORKFLOW.md](AI_WORKFLOW.md), and [Copilot instructions](../.github/copilot-instructions.md).
- Planned package structure (when created): `openwrt_imagegen/imagebuilder/`, `openwrt_imagegen/profiles/`, `openwrt_imagegen/builds/`, `openwrt_imagegen/flash/`, and a thin CLI entry point.

## 2) Bootstrap checklist (first runnable skeleton)
- Create `pyproject.toml` (Python >=3.10) with minimal deps; keep dev deps (e.g., `pytest`) separated.
- Create the package skeleton: `openwrt_imagegen/__init__.py` plus empty subpackages for imagebuilder, profiles, builds, flash.
- Add a minimal CLI: `python -m openwrt_imagegen --help` should work offline, return 0, and expose `--version`.
- Add smoke tests under `tests/` (e.g., CLI `--help`); include `pytest` config.
- Add tooling config in `pyproject.toml` for lint/format (ruff/black if adopted).
- Plan CI to mirror local commands (`pip install -e .[dev]`, `pytest`, `ruff check` / `black --check`).
- Update `README.md` and `../.github/copilot-instructions.md` when commands become real.

## 3) Dependency stack (planned)
Group dependencies in `pyproject.toml` via uv/PEP 621 optional dependency groups, with a single choice per concern:

- **Core runtime**
  - ORM + migrations: `sqlalchemy>=2` and `alembic`.
  - Database driver: built-in SQLite by default; `psycopg[binary]` as the single Postgres option when enabled.
  - Validation/config/models: `pydantic>=2`.
  - HTTP client: `httpx`.
  - CLI + progress: `typer[all]` with `rich` for output/progress.
  - Retry/backoff: `tenacity`.

- **Web + MCP (shared ASGI stack)**
  - Framework/server: `fastapi` (on Starlette) with `uvicorn[standard]`.
  - Rendering: `jinja2` for any server-rendered pages.
  - JSON serializer: `orjson`.
  - Uploads: `python-multipart` when file uploads are required.

- **Ops/safety extra**
  - Device metadata (Linux): `pyudev`.

- **Dev / QA**
  - Lint/format: `ruff` (including `ruff format`).
  - Type checking: `mypy`.
  - Tests: `pytest`, `pytest-cov`, `pytest-mock`, `pytest-asyncio` (for ASGI code).
  - HTTP mocking: `respx` (HTTPX).
  - Time control: `freezegun`.
  - Task runner: `tox` to orchestrate lint/type/test/coverage.

Keep the default install minimal (core runtime only). Use extras like `[dev]`, `[web]`, `[postgres]`, `[ops]` to keep optional features opt-in.

## 4) Common uv commands (planned once `pyproject.toml` and package exist)
- Create venv:
  ```
  uv venv .venv
  ```
- Activate:
  ```
  source .venv/bin/activate
  ```
- Install core:
  ```
  uv pip install -e .
  ```
- Install dev/tools:
  ```
  uv pip install -e .[dev]
  ```
- Install with extras:
  ```
  uv pip install -e .[dev,web,postgres]
  ```
- Lint:
  ```
  uv run ruff check
  ```
- Format check:
  ```
  uv run ruff format --check
  ```
  (or `uv run black --check` if adopted)
- Tests:
  ```
  uv run pytest
  ```
  With coverage:
  ```
  uv run pytest --cov --cov-report=term-missing
  ```
- Tox (if configured):
  ```
  uv run tox -e lint,test,coverage
  ```
- CLI smoke (once implemented):
  ```
  uv run python -m openwrt_imagegen --help
  ```
- Update lockfile:
  ```
  uv lock
  ```
  (regenerate after dependency changes)

## 5) Development workflow checklist (once code exists)

1. Create/activate venv and install dev deps:
   ```
   uv venv .venv
   source .venv/bin/activate
   uv pip install -e .[dev,web,postgres,ops]
   ```
2. Set DB (defaults to SQLite if `OWRT_IMG_DB_URL` is unset); for Postgres set `OWRT_IMG_DB_URL` and ensure server running.
3. Run migrations (after Alembic scripts exist):
   ```
   uv run alembic upgrade head
   ```
4. Lint and type check:
   ```
   uv run ruff check
   uv run ruff format --check
   uv run mypy openwrt_imagegen
   ```
5. Tests and coverage:
   ```
   uv run pytest --cov --cov-report=term-missing
   ```
6. Tox orchestration (when configured):
   ```
   uv run tox -e lint,type,test,coverage
   ```
7. Smoke CLI (once implemented):
   ```
   uv run python -m openwrt_imagegen --help
   ```

## 6) Coding style and conventions
- Python 3.10+, type hints everywhere; prefer `dataclasses` or small `TypedDict`/`Protocol`.
- Respect module boundaries: keep business logic in `openwrt_imagegen/…`; frontends stay thin.
- Errors: use explicit exception types (see [OPERATIONS.md](OPERATIONS.md) for taxonomy); propagate subprocess details (exit code, stdout/stderr paths).
- Logging: stdlib `logging` with structured context (profile_id, build_id, imagebuilder release/target/subtarget, artifact_id, device path).
- Frontends: parse/validate, call core APIs, render JSON/text; stable exit codes (0 success, specific non-zero for common failures).
- Tests: pytest; prefer deterministic unit tests with fakes/mocks (no real Image Builder downloads or block devices).
- Style tools: ruff/black (or equivalent) configs in `pyproject.toml`; docstrings for public APIs; brief comments only where logic is non-obvious.
- Typing: treat mypy as mandatory in CI; add `py.typed` to the package when publishing.
- Comments/docstrings: follow PEP 257 for docstrings; use Google-style docstrings for functions/methods with non-trivial parameters/returns. Inline comments should be sparse, informative, and avoid restating code.

## 7) Configuration defaults (planned)
- Cache root: `~/.cache/openwrt-imagegen/builders`
- Build working dirs: `<cache_root>/<release>/<target>/<subtarget>/builds/<profile>/<build_id>/`
- Artifact store: `~/.local/share/openwrt-imagegen/artifacts`
- Database: `~/.local/share/openwrt-imagegen/db.sqlite` (or configured DB URL)
- Profiles import/export root: repository `profiles/` unless overridden
- Env vars: `OWRT_IMG_CACHE`, `OWRT_IMG_ARTIFACTS`, `OWRT_IMG_DB_URL`, `OWRT_IMG_LOG_LEVEL`, `OWRT_IMG_TMPDIR`, `OWRT_IMG_OFFLINE`
- CLI flags should override env vars: `--cache-dir`, `--artifacts-dir`, `--db-url`, `--tmp-dir`, `--offline`
- Precedence: CLI flags > env vars > XDG defaults/repo defaults. Document any new knobs as they appear.

## 8) Testing expectations
- Add `pytest.ini`/`pyproject` config (type warnings as errors where feasible, test paths, markers like `integration`/`flash`).
- Test strategy (planned): profile validation; cache-key normalization; Image Builder management (mocked downloads); build pipeline with fake subprocess; flashing via temp files and hash verification; CLI/MCP parsing and JSON outputs.
- Isolation: offline by default; no real `/dev/sdX`; temporary dirs for cache/artifacts/DB; clean up via fixtures.
- Workflow: add failing test first when practical; cover happy and key failure paths; update docs when behavior/config changes.

## 9) Operational safeguards
- Flashing may need elevated permissions; require explicit `--force`/policy, never auto-elevate. Follow [SAFETY.md](SAFETY.md) and [OPERATIONS.md](OPERATIONS.md).
- Downloads must use official OpenWrt sources; honor offline mode; record checksums/URLs.
- Avoid symlink traversal/path escapes when unpacking archives or handling overlays.

## 10) Release/CI hygiene
- Use SemVer for package/CLI; expose version via CLI. Maintain migrations once ORM exists.
- Plan to add `CHANGELOG.md` when code ships; document migrations and support changes.
- Keep [OPERATIONS.md](OPERATIONS.md) updated with error codes, security constraints, and release process; keep this file current as commands and tooling evolve.
