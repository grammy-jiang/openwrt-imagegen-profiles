# OPERATIONS – errors, security, releases

Operational guardrails for builds and flashing, shared error/logging conventions, and release/versioning rules. This complements [SAFETY.md](SAFETY.md) and the design docs.

## Error taxonomy and logging (planned)
- Error classes: `ValidationError`, `NotFoundError`, `PreconditionError`, `BuildError`, `CacheConflictError`, `FlashError`, `DownloadError`, `PermissionError`.
- Each error should expose a stable `code` (e.g., `validation`, `not_found`, `build_failed`, `flash_hash_mismatch`) for CLI JSON / MCP responses.
- Logging: use stdlib `logging` with structured context (profile_id, build_id, imagebuilder release/target/subtarget, cache_key, artifact_id, device path, request id).
- On subprocess failure, log command, cwd, exit code, and stdout/stderr paths (truncate inline logs, keep full logs on disk).
- Flashing logs include bytes written and verification mode/result. Avoid PII; include device model/serial only when explicitly provided.
- CLI exit codes should align with error classes; JSON outputs should include `code`, `message`, `details`, and `log_path` when available.

## Security and operational guardrails
- Run non-root by default; flashing may need elevation—require explicit `--force`/policy, never auto-elevate.
- Never flash partitions; only explicit whole-device paths (e.g., `/dev/sdX`). Follow all rules in [SAFETY.md](SAFETY.md).
- Use official OpenWrt sources; record URLs and checksums; verify signatures when available. Honor offline mode (`OWRT_IMG_OFFLINE` / `--offline`).
- Filesystem hygiene: keep caches/artifacts under user-owned paths; guard against path traversal when unpacking archives or handling overlays; avoid world-writable outputs.
- Deployment: do not expose flashing endpoints publicly; allow disabling flashing entirely; consider rate limits/concurrency caps for builds.

## Release and versioning rules
- Use SemVer for package/CLI (`MAJOR.MINOR.PATCH`); expose version via CLI.
- MAJOR for breaking CLI/API or incompatible schema migrations; MINOR for backward-compatible features; PATCH for fixes/docs.
- Maintain migrations (e.g., Alembic) once ORM exists; keep them reversible when practical and document rationale.
- Keep `CHANGELOG.md` (once code ships) with Added/Changed/Fixed/Removed, migrations, and OpenWrt support changes.
- Document tested/supported OpenWrt releases/targets in README once implementation exists; mark deprecated Image Builders in APIs as needed.
- Update `../.github/copilot-instructions.md`, `../README.md`, and [DEVELOPMENT.md](DEVELOPMENT.md) when release processes or defaults change.
