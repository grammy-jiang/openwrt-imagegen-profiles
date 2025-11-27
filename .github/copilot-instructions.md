# Copilot Instructions for `openwrt-imagegen-profiles`

These instructions guide AI coding agents working in this repository. They are a **short, operational summary** of `README.md`, `ARCHITECTURE.md`, and `AI_CONTRIBUTING.md`.

## 1. Big picture (what this repo does)

- Provide an **AI-friendly orchestration layer** around the official **OpenWrt Image Builder**.
- Manage **profiles, Image Builder metadata, builds, and artifacts via a database + ORM**.
- Safely **flash TF/SD cards** from built images.
- Expose the same core logic through three frontends:
  - CLI (primary today, CI-friendly).
  - Web interface (thin GUI).
  - MCP server (AI tools call into builds/flash).

This is **not** a generic OpenWrt SDK; always shell out to the official Image Builder for firmware builds.

## 2. Architecture & boundaries

- Treat **profiles as data, Python as orchestration logic**:
  - Profiles encode: device ID, OpenWrt release, target/subtarget, Image Builder profile, packages, overlays/policies.
  - Python code: resolves Image Builder downloads, builds images, tracks artifacts, orchestrates TF card flashing.
- Database + ORM are the **source of truth** for:
  - Profiles, Image Builder variants, build records, artifact paths, cache metadata.
  - YAML/JSON/TOML under `profiles/` are **import/export only**, not authoritative.
- Frontends (CLI, web, MCP) are **thin wrappers**:
  - Parse/validate input → call core library → format output.
  - No build/flash logic in CLI commands, HTTP handlers, or MCP handlers.

If you add new behaviors, put them in the core library first, then lightly wire them through frontends.

## 3. Code layout expectations

Even if not all modules exist yet, follow the planned structure from `ARCHITECTURE.md`:

- `openwrt_imagegen/`
  - `imagebuilder/` – download + cache official Image Builder, ORM model for cached builders.
  - `profiles/` – ORM models + APIs for profile CRUD and validation.
  - `builds/` – compose Image Builder commands, run builds, record artifacts + build history, implement image cache.
  - `flash/` – TF/SD card flashing workflows and safety checks.
  - `cli.py` / `__main__.py` – thin CLI entrypoint over the above.
- `web/` – HTTP handlers that call the same Python APIs (no new business logic).
- `mcp_server/` – MCP tools that forward to the same Python APIs.
- `profiles/` – optional on-disk profile exports + schema helpers.
- `tests/` – mirror the package layout when adding tests.

Do not invent new top-level packages for core logic without also updating `ARCHITECTURE.md`.

## 4. Core behavioral rules for AI changes

- **Reproducibility first**
  - Inputs to a build are: profile + Image Builder version + explicit options. Same inputs must yield same outputs.
  - Avoid hidden globals ("current device", implicit release); pass explicit context objects/arguments.
- **Profiles are immutable inputs**
  - Never mutate profile ORM instances during a build; derive new structures instead.
  - Changing device behavior means creating/updating a profile, not patching it mid-build.
- **Centralized command construction**
  - All Image Builder command lines should be constructed in one place under `openwrt_imagegen/builds/`.
  - Frontends must not shell out directly.
- **Image cache via DB**
  - Before building, check DB-backed cache for an existing artifact with identical effective inputs.
  - Expose both "build-or-reuse" (idempotent default) and "force rebuild" paths.

## 5. TF/SD card flashing safety

Any change under `openwrt_imagegen/flash/` must preserve these invariants:

- Only operate on **explicit whole-device paths** (e.g. `/dev/sdX`, never `/dev/sdX1`).
- **No guessing devices** based on size/labels; callers must pass the device path.
- Provide **dry-run** and explicit **force** flags for destructive operations.
- Perform pre-flight checks (block device existence, permissions, optional wipe of old signatures).
- Writes must be **fully flushed** (fsync/sync semantics) before reporting success.
- Verify by **hashing device contents vs source image** (full or well-documented prefix).
- Treat mismatched hashes as a failure and log clearly; support marking devices/cards as suspect in metadata/logs.

If a change weakens any of these guarantees, do not make it.

## 6. Developer workflows to align with

When adding scripts, CLIs, or MCP/web endpoints, model them on these flows:

- **Build image for a profile**
  - Input: profile ID (or definition) + options.
  - Steps: ensure Image Builder (download/cache) → compute cache key → build-or-reuse → store build record + artifacts in a structured tree (e.g. `builds/<device>/<release>/build-<timestamp>/`).
- **List and inspect builds**
  - Query DB for latest successful build(s) by profile, release, or Image Builder variant.
  - Return paths, checksums, and status for use by CI or MCP clients.
- **Flash TF card**
  - Input: explicit image path or build ID + explicit device path.
  - Steps: pre-flight checks → optional wipe → write with flush → hash-verify → log and return rich metadata.

Design CLIs and MCP endpoints so they can run **non-interactively** with well-defined exit codes and optional JSON output.

## 7. How AI agents should work here

- Before adding new behavior, skim `README.md`, `ARCHITECTURE.md`, and `AI_CONTRIBUTING.md` to mirror existing patterns.
- Keep public APIs stable; if you must change a function/CLI signature, update all call sites and adjust docs/tests in the same PR.
- Prefer clear, composable Python APIs (e.g. `build_or_reuse_image(profile_id, options)`, `flash_device(image_path, device, *, dry_run, force)`) over ad-hoc scripts.
- When in doubt, favor **clarity, reproducibility, and safety** over cleverness or convenience.

If repository reality ever diverges from these instructions, follow the actual code and update this file to match.
