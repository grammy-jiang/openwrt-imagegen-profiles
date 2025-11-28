# INTERFACES – CLI and MCP contracts

Frontends are thin shells over `openwrt_imagegen` APIs. This doc captures the planned shapes for the CLI and MCP server so implementations stay aligned.

## CLI (planned)
- Global: `imagegen --version`; `--json` for structured output; common options `--db-url`, `--cache-dir`, `--artifacts-dir`, `--tmp-dir`, `--offline`, `--log-level`.
- Profiles: list/show/import/export; create/update once DB CRUD exists.
  - `imagegen profiles list [--tag TAG ...] [--release R] [--target T] [--subtarget S]`
  - `imagegen profiles show --profile-id ID`
  - `imagegen profiles import FILE`
  - `imagegen profiles export --profile-id ID [-o FILE|-]`
- Image Builder cache:
  - `imagegen builders ensure --release R --target T --subtarget S`
  - `imagegen builders list [--release R] [--target T] [--subtarget S]`
  - `imagegen builders prune [--unused-only]`
- Builds:
  - `imagegen build --profile-id ID [--extra-package PKG ...] [--remove-package PKG ...] [--extra-image-name NAME] [--bin-dir PATH] [--force-rebuild] [--initramfs]`
  - `imagegen builds list [--profile-id ID] [--status succeeded|failed|running|pending]`
  - `imagegen builds show --build-id BID`
- Artifacts:
  - `imagegen artifacts list --build-id BID`
  - `imagegen artifacts show --artifact-id AID`
- Flashing:
  - `imagegen flash --artifact-id AID --device /dev/sdX [--verify {full,prefix-64m}] [--wipe] [--dry-run] [--force]`
  - `imagegen flash --image-path PATH --device /dev/sdX ...` (explicit image path)
- JSON output sketches:
  - Profile: `{"profile_id": "...", "name": "...", "openwrt_release": "...", "target": "...", "subtarget": "...", "imagebuilder_profile": "...", "tags": [...] }`
  - ImageBuilder: `{"id": "...", "release": "...", "target": "...", "subtarget": "...", "state": "...", "cache_root": "..." }`
  - Build: `{"id": "...", "profile_id": "...", "imagebuilder": {...}, "status": "...", "cache_hit": true|false, "artifacts": [...], "log_path": "..." }`
  - Artifact: `{"id": "...", "build_id": "...", "kind": "...", "path": "...", "sha256": "...", "size_bytes": ... }`
  - Flash result: `{"status": "succeeded|failed", "device": "/dev/sdX", "artifact_id": "...", "bytes_written": ..., "verification": {"mode": "full|prefix-64m", "result": "match|mismatch"}, "log_path": "..." }`
- Exit codes: 0 success/cache hit; prefer dedicated codes for validation, not-found, build failed, flash failed (see [OPERATIONS.md](OPERATIONS.md)).

## MCP tools (planned)
- Tools: `list_profiles`, `get_profile`, `build_image`, `list_builds`, `get_build`, `list_artifacts`, `flash_artifact`.
- Sample `build_image` request/response:
  ```json
  {
    "profile_id": "home.ap-livingroom.23.05",
    "options": {
      "extra_packages": ["tcpdump"],
      "remove_packages": [],
      "extra_image_name": "lab-debug",
      "bin_dir": null,
      "force_rebuild": false,
      "initramfs": false
    }
  }
  ```
  Response: `{"build": { "id": "...", "profile_id": "...", "status": "succeeded|failed|running|pending", "cache_hit": true, "artifacts": [...], "log_path": "..." } }`
- Sample `flash_artifact` request/response:
  ```json
  {
    "artifact_id": "...",
    "device": "/dev/sdX",
    "verify_mode": "full|prefix-64m",
    "wipe": false,
    "dry_run": false,
    "force": true
  }
  ```
  Response: `{ "flash": { "status": "succeeded|failed", "device": "/dev/sdX", "artifact_id": "...", "bytes_written": ..., "verification": {"mode": "...", "result": "match"}, "log_path": "..." } }`
- Semantics:
  - `build_image` is idempotent; identical inputs → cache hit unless `force_rebuild`.
  - `flash_artifact` never guesses devices; explicit `device` required.
  - Errors return structured `code` strings and optional `log_path` (see [OPERATIONS.md](OPERATIONS.md)).
- Transport/auth: transport can vary (HTTP, stdio, etc.); keep tool contracts consistent. Guard flashing endpoints; require explicit enablement in any deployment.
