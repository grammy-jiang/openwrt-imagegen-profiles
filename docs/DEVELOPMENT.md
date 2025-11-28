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

## 3) Coding style and conventions
- Python 3.10+, type hints everywhere; prefer `dataclasses` or small `TypedDict`/`Protocol`.
- Respect module boundaries: keep business logic in `openwrt_imagegen/…`; frontends stay thin.
- Errors: use explicit exception types (see [OPERATIONS.md](OPERATIONS.md) for taxonomy); propagate subprocess details (exit code, stdout/stderr paths).
- Logging: stdlib `logging` with structured context (profile_id, build_id, imagebuilder release/target/subtarget, artifact_id, device path).
- Frontends: parse/validate, call core APIs, render JSON/text; stable exit codes (0 success, specific non-zero for common failures).
- Tests: pytest; prefer deterministic unit tests with fakes/mocks (no real Image Builder downloads or block devices).
- Style tools: ruff/black (or equivalent) configs in `pyproject.toml`; docstrings for public APIs; brief comments only where logic is non-obvious.

## 4) Configuration defaults (planned)
- Cache root: `~/.cache/openwrt-imagegen/builders`
- Build working dirs: `<cache_root>/<release>/<target>/<subtarget>/builds/<profile>/<build_id>/`
- Artifact store: `~/.local/share/openwrt-imagegen/artifacts`
- Database: `~/.local/share/openwrt-imagegen/db.sqlite` (or configured DB URL)
- Profiles import/export root: repository `profiles/` unless overridden
- Env vars: `OWRT_IMG_CACHE`, `OWRT_IMG_ARTIFACTS`, `OWRT_IMG_DB_URL`, `OWRT_IMG_LOG_LEVEL`, `OWRT_IMG_TMPDIR`, `OWRT_IMG_OFFLINE`
- CLI flags should override env vars: `--cache-dir`, `--artifacts-dir`, `--db-url`, `--tmp-dir`, `--offline`
- Precedence: CLI flags > env vars > XDG defaults/repo defaults. Document any new knobs as they appear.

## 5) Testing expectations
- Add `pytest.ini`/`pyproject` config (type warnings as errors where feasible, test paths, markers like `integration`/`flash`).
- Test strategy (planned): profile validation; cache-key normalization; Image Builder management (mocked downloads); build pipeline with fake subprocess; flashing via temp files and hash verification; CLI/MCP parsing and JSON outputs.
- Isolation: offline by default; no real `/dev/sdX`; temporary dirs for cache/artifacts/DB; clean up via fixtures.
- Workflow: add failing test first when practical; cover happy and key failure paths; update docs when behavior/config changes.

## 6) Operational safeguards
- Flashing may need elevated permissions; require explicit `--force`/policy, never auto-elevate. Follow [SAFETY.md](SAFETY.md) and [OPERATIONS.md](OPERATIONS.md).
- Downloads must use official OpenWrt sources; honor offline mode; record checksums/URLs.
- Avoid symlink traversal/path escapes when unpacking archives or handling overlays.

## 7) Release/CI hygiene
- Use SemVer for package/CLI; expose version via CLI. Maintain migrations once ORM exists.
- Plan to add `CHANGELOG.md` when code ships; document migrations and support changes.
- Keep [OPERATIONS.md](OPERATIONS.md) updated with error codes, security constraints, and release process; keep this file current as commands and tooling evolve.
