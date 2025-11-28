# Development Guide

This repository is currently design-heavy: the core Python package has not been implemented yet. Use this guide as the single place for day-to-day engineering info: bootstrap, style, configuration defaults, testing expectations, and working practices.

## 1) Status and layout
- Code status: design docs + profile examples only; no `openwrt_imagegen/` package or tests yet.
- Key design references: [README.md](../README.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PROFILES.md](PROFILES.md), [BUILD_PIPELINE.md](BUILD_PIPELINE.md), [SAFETY.md](SAFETY.md), [DB_MODELS.md](DB_MODELS.md), [FRONTENDS.md](FRONTENDS.md), [AI_CONTRIBUTING.md](AI_CONTRIBUTING.md), [AI_WORKFLOW.md](AI_WORKFLOW.md), and [Copilot instructions](../.github/copilot-instructions.md).
- Planned package structure (when created): `openwrt_imagegen/imagebuilder/`, `openwrt_imagegen/profiles/`, `openwrt_imagegen/builds/`, `openwrt_imagegen/flash/`, and a thin CLI entry point.

## 2) Bootstrap checklist (first runnable skeleton)
- Create `pyproject.toml` (Python >=3.10) with minimal deps; keep dev deps (e.g., `pytest`) separated.
- Create the package skeleton: `openwrt_imagegen/__init__.py` plus empty subpackages for imagebuilder, profiles, builds, flash, and a shared `types.py`.
- Add a minimal CLI: `python -m openwrt_imagegen --help` should work offline, return 0, and expose `--version`.
- Add smoke tests under `tests/` (e.g., CLI `--help`); include `pytest` config.
- Add tooling config in `pyproject.toml` for lint/format (ruff/black if adopted).
- Plan CI to mirror local commands (`pip install -e .[dev]`, `pytest`, `ruff check` / `black --check`).
- Update `README.md` and `../.github/copilot-instructions.md` when commands become real.

## 3) Suggested implementation route

1. **Scaffold**  
   - Add `pyproject.toml` with core + dev extras (per Section 3), `src` layout or flat package root, `uv.lock`, and basic tool configs (ruff, mypy, pytest).
   - Create `openwrt_imagegen/` skeleton (subpackages + `types.py`) and `tests/` with a CLI smoke test.
   - Add CI (GitHub Actions) to run ruff, mypy, pytest with coverage on pushes/PRs.

2. **Config + logging foundation**  
   - Implement `config.py` (pydantic Settings) with paths, concurrency, offline mode, verification mode; expose `print-config` in CLI.
   - Set up logging config helper to emit structured logs; include request IDs.

3. **ORM models + DB plumbing**  
   - Define models in `profiles/models.py`, `imagebuilder/models.py`, `builds/models.py`, optional `flash/models.py`; integrate SQLAlchemy session management.
   - Add Alembic with initial migration; add tests for model creation and basic CRUD.

4. **Profile validation + import/export**  
   - Implement `profiles/schema.py` (Pydantic), `profiles/io.py`, `profiles/service.py` for CRUD/query/import/export; tests for validation and bulk import/export reporting.

5. **Image Builder management**  
   - Implement URL discovery, download with checksum/signature verification, extraction, and metadata updates; locking for downloads.  
   - Tests with mocked HTTP and temp dirs; ensure cache metadata persisted.

6. **Build orchestration**  
   - Implement cache-key computation (`builds/cache_key.py`), overlay staging/hashing (`builds/overlay.py`), runner (`builds/runner.py`), artifact discovery/manifests (`builds/artifacts.py`), and `build_or_reuse` in `builds/service.py` with locking/concurrency.  
   - Tests using fakes/mocks for subprocess and filesystem.

7. **Batch builds**  
   - Implement `build_batch` with filter resolution, per-profile results, fail-fast vs best-effort modes; respect concurrency limits.  
   - Tests for mixed cache hits/misses and failure aggregation.

8. **Flashing workflows**  
   - Implement device validation (`flash/device.py`), writer (`flash/writer.py`), service (`flash/service.py`) with dry-run/force/wipe/verify; optional FlashRecord persistence.  
   - Tests using temp files as fake devices; hash verification logic.

9. **CLI**  
   - Implement Typer-based CLI mapping to services (profiles, builders, builds, batch, artifacts, flash); support `--json`, exit codes per `OPERATIONS.md`, and config printing.  
   - Tests for argument parsing and JSON outputs.

10. **Web API**  
    - Build FastAPI app exposing endpoints per `FRONTENDS.md` (profiles, builders, builds, batch, artifacts, flash); reuse core services and schemas; enable polling endpoints for status/logs.  
    - Tests with TestClient for happy/error paths.

11. **MCP server**  
    - Implement Starlette/FastAPI MCP tools (`list_profiles`, `build_image`, `build_images_batch`, `list_builds`, `list_artifacts`, `flash_artifact`); ensure idempotency, structured errors, and log path exposure.  
    - Tests for tool behaviors and error codes.

12. **Docs & polish**  
    - Update `README.md`, `docs/DEVELOPMENT.md`, `.github/copilot-instructions.md` with actual commands and status.  
    - Add `CHANGELOG.md` and package markers (`py.typed`) when publishing.

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
