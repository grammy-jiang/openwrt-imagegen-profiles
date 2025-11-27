# AI coding agent guidelines for `openwrt-imagegen-profiles`

This project is an AI-friendly orchestration layer for building and managing OpenWrt images. Treat `ARCHITECTURE.md` as the **single source of truth** for how the system should work; keep everything you add consistent with it.

## Big-picture intent

- The core goal: **reproducible, cache-aware OpenWrt Image Builder runs plus safe TF/SD card flashing**, driven by Python orchestration.
- All frontends (CLI, web, MCP) are **thin shells** over a shared Python library; do not duplicate business logic in UI or server layers.
- Profiles are **declarative, immutable inputs**; build records and caches are the **observable history**.

## Where to put new code

Follow the planned layout in `ARCHITECTURE.md`:

- Put orchestration/business logic in a package like `openwrt_imagegen/` (or whatever is already used in code once it exists).
  - `imagebuilder/`: fetch & cache official OpenWrt Image Builder archives; no custom firmware logic.
  - `profiles/`: ORM models + validation for device profiles.
  - `builds/`: build orchestration, image cache, build records.
  - `flash/`: TF card write flows and safety checks only.
- Keep `cli` / `web` / `mcp_server` layers **very thin**:
  - Parse/validate input.
  - Call library functions.
  - Format output (human text, JSON, HTTP, MCP protocol).

If the package structure does not exist yet, create it following the names and responsibilities above rather than inventing new ones.

## Key design constraints

- **Reproducibility**

  - A build must be determined by: profile + Image Builder version + explicit options.
  - Never mutate profile data during a build; derive new behavior from new profiles or explicit flags.
  - When adding features, prefer additional explicit inputs over hidden global configuration.

- **Separation of concerns**

  - Profiles are data; orchestrator is logic; frontends are adapters.
  - Database/ORM access belongs in dedicated modules (e.g. `profiles`, `builds`), not in CLI argument parsing or HTTP handlers.

- **Safety around TF card flashing**
  - Never guess block devices; require explicit device paths and, ideally, explicit "force" flags.
  - Provide dry-run/preview operations and detailed logs.
  - After writes, support verification by hashing data read back from the device.
  - Integrate with build metadata where possible (e.g. unique build IDs) to enable post-boot validation.

## External integration patterns

- Always shell out to the **official OpenWrt Image Builder** for building images; do not re-implement low-level firmware assembly.
- Cache downloaded Image Builder archives by `(release, target, subtarget)` and record them in the database so builds can refer back to the exact toolchain used.
- When you add MCP or web endpoints, map each operation directly to an existing Python API:
  - "ensure image builder", "build-or-reuse image for profile", "list builds", "flash this image to this device".
  - Keep endpoints **idempotent where possible** (e.g. build-or-reuse semantics keyed by inputs).

## Developer workflows (for you and other agents)

- Before implementing features, skim `ARCHITECTURE.md` to understand the intended module boundaries and names.
- When adding commands/endpoints, design them so that:
  - CLI can return **structured (JSON) output** alongside human-readable text.
  - MCP/web can retrieve enough metadata (IDs, statuses, paths) to orchestrate follow-up steps.
- Prefer small, composable Python functions that:
  - Take explicit, typed inputs (profile IDs, releases, targets, options).
  - Return structured results (objects, dataclasses, or dicts) that can be serialized for CLI/web/MCP.

## Conventions to follow

- Treat the **database as the source of truth** for profiles, cached Image Builders, build records, and artifact metadata.
- When a DB is not available, support minimal fallback (e.g. in-memory or file-backed profiles) but keep the API shape the same.
- Log all destructive or expensive operations clearly (downloads, builds, flashes) and surface errors rather than hiding them.
- When in doubt, align new behavior with the narrative and terminology in `ARCHITECTURE.md` and `README.md` instead of inventing new abstractions.
