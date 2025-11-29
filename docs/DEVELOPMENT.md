# Development Guide

This repository provides an opinionated Python library for managing OpenWrt Image Builder workflows. Use this guide as the single place for day-to-day engineering info: bootstrap, style, configuration defaults, testing expectations, and working practices.

## 1) Status and layout

- Code status: **core library, CLI, web API, MCP server, and DB models implemented** with comprehensive tests.
- Package structure: `openwrt_imagegen/imagebuilder/`, `openwrt_imagegen/profiles/`, `openwrt_imagegen/builds/`, `openwrt_imagegen/flash/`, `openwrt_imagegen/config.py`, `openwrt_imagegen/types.py`, and a Typer-based CLI in `openwrt_imagegen/cli.py`.
- Tests: `tests/` with coverage for CLI, config, types, profiles, imagebuilder, builds, flash, web API, and MCP tools.
- Key design references: [README.md](../README.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PROFILES.md](PROFILES.md), [BUILD_PIPELINE.md](BUILD_PIPELINE.md), [SAFETY.md](SAFETY.md), [DB_MODELS.md](DB_MODELS.md), [FRONTENDS.md](FRONTENDS.md), [AI_CONTRIBUTING.md](AI_CONTRIBUTING.md), [AI_WORKFLOW.md](AI_WORKFLOW.md), and [Copilot instructions](../.github/copilot-instructions.md).

## 2) Bootstrap checklist (current)

- [x] Create `pyproject.toml` (Python >=3.10) with minimal deps; keep dev deps separated.
- [x] Implement `openwrt_imagegen/` with subpackages for imagebuilder, profiles, builds, flash, plus shared `types.py`, `config.py`, `db.py`, and `cli.py`.
- [x] Implement CLI: `python -m openwrt_imagegen --help` works offline, returns 0, and exposes `--version` and subcommands for profiles, builders, builds, artifacts, and flash.
- [x] Add tests under `tests/` for CLI, config, types, profiles, imagebuilder, builds, flash, web API, and MCP tools.
- [x] Add tooling config in `pyproject.toml` for lint/format (ruff), mypy, and pytest.
- [x] Add `py.typed` marker for typed package.
- [ ] Add CI (GitHub Actions) to run ruff, mypy, pytest with coverage on pushes/PRs.

## 3) Suggested implementation route

1. **Scaffold** ✅ (completed)

   - Added `pyproject.toml` with core + dev extras, `uv.lock`, and basic tool configs (ruff, mypy, pytest).
   - Created `openwrt_imagegen/` skeleton (subpackages + `types.py`) and `tests/` with CLI smoke tests.
   - Remaining: Add CI (GitHub Actions) to run ruff, mypy, pytest with coverage on pushes/PRs.

2. **Config + logging foundation** ✅ (partially completed)

   - Implemented `config.py` (pydantic Settings) with paths, concurrency, offline mode, verification mode; exposed `config` command in CLI.
   - Remaining: Set up logging config helper to emit structured logs; include request IDs.

3. **ORM models + DB plumbing** ✅ (completed)

   - Defined models in `profiles/models.py` (Profile), `imagebuilder/models.py` (ImageBuilder), `builds/models.py` (BuildRecord, Artifact), `flash/models.py` (FlashRecord).
   - Added `db.py` with SQLAlchemy engine, session management, and Base model.
   - Added Alembic with initial migration (`alembic/versions/`).
   - Added comprehensive CRUD tests in `tests/test_models.py`.

4. **Profile validation + import/export** ✅ (completed)

   - Implemented `profiles/schema.py` with Pydantic models for profile validation.
   - Implemented `profiles/io.py` for YAML/JSON import/export.
   - Implemented `profiles/service.py` for CRUD/query/import/export operations.
   - Added CLI commands: `profiles list`, `profiles show`, `profiles import`, `profiles export`, `profiles validate`.
   - Added comprehensive tests in `tests/test_profiles_schema.py`, `tests/test_profiles_io.py`, `tests/test_profiles_service.py`.

5. **Image Builder management** ✅ (completed)

- Implemented URL discovery, download with checksum verification, extraction, and metadata updates with locking for downloads.
- Tests with mocked HTTP and temp dirs; cache metadata persisted in the database.

6. **Build orchestration** ✅ (completed)

- Implemented cache-key computation (`builds/cache_key.py`), overlay staging/hashing (`builds/overlay.py`), runner (`builds/runner.py`), artifact discovery/manifests (`builds/artifacts.py`), and `build_or_reuse` in `builds/service.py` with locking.
- Tests use fakes/mocks for subprocess and filesystem; batch behavior is covered via `build_batch` tests.

7. **Batch builds** ✅ (completed)

- Implemented `build_batch` with filter resolution, per-profile results, fail-fast vs best-effort modes.
- Tests for mixed cache hits/misses and failure aggregation.

8. **Flashing workflows** ✅ (completed)

- Implemented device validation (`flash/device.py`), writer (`flash/writer.py`), service (`flash/service.py`) with dry-run/force/wipe/verify and FlashRecord persistence.
- Tests use temp files as fake devices; hash verification logic is exercised end-to-end.

9. **CLI** ✅ (completed)

- Implemented Typer-based CLI mapping to services (profiles, builders, builds, batch, artifacts, flash); supports `--json`, structured errors, and config printing.
- Tests validate argument parsing and JSON output shapes.

10. **Web API** ✅ (completed)

    - Implemented FastAPI app in `web/` exposing endpoints per `FRONTENDS.md`:
      - Health/root endpoints: `GET /health`, `GET /`
      - Config: `GET /config`
      - Profiles: `GET /profiles`, `GET /profiles/{id}`, `POST /profiles`, `PUT /profiles/{id}`, `DELETE /profiles/{id}`
      - Builders: `GET /builders`, `GET /builders/{release}/{target}/{subtarget}`, `POST /builders/ensure`, `POST /builders/prune`, `GET /builders/info`
      - Builds: `GET /builds`, `GET /builds/{id}`, `GET /builds/{id}/artifacts`, `POST /builds/batch`
      - Flash: `GET /flash`, `POST /flash`
    - Reuses core services and schemas; returns structured JSON with error codes.
    - Tests with TestClient for happy and error paths in `tests/test_web_api.py`.

11. **MCP server** ✅ (completed)

    - Implemented FastMCP server in `mcp_server/` exposing tools per `FRONTENDS.md`:
      - `list_profiles` - list profiles with optional filters
      - `get_profile` - get profile details by ID
      - `build_image` - build-or-reuse with idempotent semantics (returns cache_hit flag)
      - `build_images_batch` - batch builds with fail-fast/best-effort modes
      - `list_builds` - list build records with filters
      - `list_artifacts` - list artifacts with filters
      - `flash_artifact` - flash with safety checks (requires force=True for actual writes)
    - Structured error responses with stable codes per `OPERATIONS.md` taxonomy.
    - Tests for idempotency and error codes in `tests/test_mcp_tools.py`.

12. **Docs & polish** ✅ (in progress)

- Keep `README.md`, `docs/DEVELOPMENT.md`, `.github/copilot-instructions.md`, and other docs aligned with the implemented code.
- Add `CHANGELOG.md` when publishing.

## 4) Dependency stack (implemented)

Group dependencies in `pyproject.toml` via uv/PEP 621 optional dependency groups, with a single choice per concern:

- **Core runtime**

  - ORM + migrations: `sqlalchemy>=2` and `alembic`.
  - Database driver: built-in SQLite by default; `psycopg[binary]` as the single Postgres option when enabled.
  - Validation/config/models: `pydantic>=2`.
  - HTTP client: `httpx`.
  - CLI + progress: `typer[all]` with `rich` for output/progress.
  - Retry/backoff: `tenacity`.
  - YAML parsing: `pyyaml>=6`.

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

## 5) Common uv commands

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
- CLI smoke:
  ```
  uv run python -m openwrt_imagegen --help
  ```
- Profile commands:
  ```
  uv run python -m openwrt_imagegen profiles --help
  uv run python -m openwrt_imagegen profiles validate profiles/home-ap-livingroom.yaml
  uv run python -m openwrt_imagegen profiles import profiles/
  uv run python -m openwrt_imagegen profiles list
  uv run python -m openwrt_imagegen profiles list --json
  uv run python -m openwrt_imagegen profiles list --target ath79 --json
  uv run python -m openwrt_imagegen profiles list --release 23.05.2 --json
  uv run python -m openwrt_imagegen profiles show <profile-id>
  ```
- Build commands:
  ```
  uv run python -m openwrt_imagegen build --help
  uv run python -m openwrt_imagegen build list --json
  uv run python -m openwrt_imagegen build batch --profile <profile-id> --json
  ```
- Artifact commands:
  ```
  uv run python -m openwrt_imagegen artifacts --help
  uv run python -m openwrt_imagegen artifacts list --json
  uv run python -m openwrt_imagegen artifacts list --build-id <build-id> --json
  uv run python -m openwrt_imagegen artifacts show <artifact-id> --json
  ```
- Flash commands:
  ```
  uv run python -m openwrt_imagegen flash --help
  uv run python -m openwrt_imagegen flash image <image-path> <device> --dry-run --force --json
  uv run python -m openwrt_imagegen flash write <artifact-id> <device> --dry-run --force --json
  uv run python -m openwrt_imagegen flash list --json
  uv run python -m openwrt_imagegen flash list --status succeeded --json
  ```
- Web API server:
  ```
  uv run uvicorn web:app --reload --host 0.0.0.0 --port 8000
  ```
  Then access: `http://localhost:8000/docs` for OpenAPI documentation.
- MCP server (for AI tools):
  ```
  uv pip install -e .[mcp]
  ```
  The MCP server can be imported and run via `mcp_server.mcp`. Tools exposed:
  - `list_profiles`, `get_profile`: Profile queries
  - `build_image`, `build_images_batch`: Build operations with idempotent (cache-aware) semantics
  - `list_builds`, `list_artifacts`: Build/artifact queries
  - `flash_artifact`: Flash operations (requires `force=True` for actual writes)
- Update lockfile:
  ```
  uv lock
  ```
  (regenerate after dependency changes)

## 6) Development workflow checklist

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
7. Smoke CLI:
   ```
   uv run python -m openwrt_imagegen --help
   ```

## 7) Coding style and conventions

- Python 3.10+, type hints everywhere; prefer `dataclasses` or small `TypedDict`/`Protocol`.
- Respect module boundaries: keep business logic in `openwrt_imagegen/…`; frontends stay thin.
- Errors: use explicit exception types (see [OPERATIONS.md](OPERATIONS.md) for taxonomy); propagate subprocess details (exit code, stdout/stderr paths).
- Logging: stdlib `logging` with structured context (profile_id, build_id, imagebuilder release/target/subtarget, artifact_id, device path).
- Frontends: parse/validate, call core APIs, render JSON/text; stable exit codes (0 success, specific non-zero for common failures).
- Tests: pytest; prefer deterministic unit tests with fakes/mocks (no real Image Builder downloads or block devices).
- Style tools: ruff/black (or equivalent) configs in `pyproject.toml`; docstrings for public APIs; brief comments only where logic is non-obvious.
- Typing: treat mypy as mandatory in CI; `py.typed` marker added to the package.
- Comments/docstrings: follow PEP 257 for docstrings; use Google-style docstrings for functions/methods with non-trivial parameters/returns. Inline comments should be sparse, informative, and avoid restating code.

## 8) Configuration defaults (implemented)

- Cache root: `~/.cache/openwrt-imagegen/builders`
- Build working dirs: `<cache_root>/<release>/<target>/<subtarget>/builds/<profile>/<build_id>/`
- Artifact store: `~/.local/share/openwrt-imagegen/artifacts`
- Database: `~/.local/share/openwrt-imagegen/db.sqlite` (or configured DB URL)
- Profiles import/export root: repository `profiles/` unless overridden
- Env vars: `OWRT_IMG_CACHE_DIR`, `OWRT_IMG_ARTIFACTS_DIR`, `OWRT_IMG_DB_URL`, `OWRT_IMG_LOG_LEVEL`, `OWRT_IMG_TMP_DIR`, `OWRT_IMG_OFFLINE`
- CLI flags should override env vars: `--cache-dir`, `--artifacts-dir`, `--db-url`, `--tmp-dir`, `--offline`
- Precedence: CLI flags > env vars > XDG defaults/repo defaults. Document any new knobs as they appear.
- View current config: `python -m openwrt_imagegen config --json`

## 9) Testing expectations

- Add `pytest.ini`/`pyproject` config (type warnings as errors where feasible, test paths, markers like `integration`/`flash`).
- Test strategy (planned): profile validation; cache-key normalization; Image Builder management (mocked downloads); build pipeline with fake subprocess; flashing via temp files and hash verification; CLI/MCP parsing and JSON outputs.
- Isolation: offline by default; no real `/dev/sdX`; temporary dirs for cache/artifacts/DB; clean up via fixtures.
- Workflow: add failing test first when practical; cover happy and key failure paths; update docs when behavior/config changes.

## 10) Operational safeguards

- Flashing may need elevated permissions; require explicit `--force`/policy, never auto-elevate. Follow [SAFETY.md](SAFETY.md) and [OPERATIONS.md](OPERATIONS.md).
- Downloads must use official OpenWrt sources; honor offline mode; record checksums/URLs.
- Avoid symlink traversal/path escapes when unpacking archives or handling overlays.

## 11) Release/CI hygiene

- Use SemVer for package/CLI; expose version via CLI. Maintain migrations once ORM exists.
- Plan to add `CHANGELOG.md` when code ships; document migrations and support changes.
- Keep [OPERATIONS.md](OPERATIONS.md) updated with error codes, security constraints, and release process; keep this file current as commands and tooling evolve.
