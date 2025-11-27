# Copilot Instructions for `openwrt-imagegen-profiles`

These instructions are the **short, AI-facing version** of `README.md`, `ARCHITECTURE.md`, and `AI_CONTRIBUTING.md`. They explain how to be productive here without fighting the design.

## 1. Big picture

- This repo wraps the **official OpenWrt Image Builder** with a Python orchestration layer that manages:
  - Declarative **device profiles**.
  - **Builds and artifacts** in a database via an ORM.
  - Safe **TF/SD card flashing**.
- Everything flows through a shared Python core; frontends (CLI, web, MCP server) are **thin adapters** over that core.
- Do **not** re‑implement OpenWrt’s build logic; always shell out to the official Image Builder.

Read next for deeper context:

- `README.md` – project purpose, frontends, and outcomes.
- `ARCHITECTURE.md` – authoritative design: data model, caching, TF flashing rules.
- `AI_CONTRIBUTING.md` – strict rules for AI changes (database/ORM, safety, layout).

## 2. Architecture & data flow

- **Profiles are immutable data** (device ID, release, target/subtarget, Image Builder profile name, packages, overlays).
- The **Python core**:
  - Resolves/ensures the right Image Builder (downloads + caches by release/target/subtarget).
  - Composes Image Builder commands from profiles + options.
  - Runs builds, collects outputs, and records **build records** (inputs, outputs, checksums, logs, status).
  - Maintains an **image cache**: same inputs ⇒ reuse existing artifacts.
- **TF card flashing** is a separate safety‑critical layer that:
  - Only writes to explicit whole‑device paths (e.g. `/dev/sdX`).
  - Flushes writes and verifies via hash read‑back.
  - Detects/flags ghost writes or bad cards.

Always keep build and flash behavior in reusable Python modules; CLIs, web handlers, and MCP tools should just call those.

## 3. Code layout expectations

Even if not all modules exist yet, follow the planned layout from `ARCHITECTURE.md` / `AI_CONTRIBUTING.md`:

- `openwrt_imagegen/` (core library)
  - `imagebuilder/` – download/cache Image Builder; ORM model for cached builders.
  - `profiles/` – ORM models + APIs for profile CRUD and validation.
  - `builds/` – build orchestration, cache key logic, build records, artifact tracking.
  - `flash/` – TF/SD card flashing workflows and safety checks.
  - `cli.py` / `__main__.py` – thin CLI wrapper over these APIs.
- `web/` – optional web UI; HTTP handlers should only call core APIs.
- `mcp_server/` – MCP server mapping protocol calls to core APIs one‑for‑one.
- `profiles/` (top‑level) – optional import/export of profiles (YAML/JSON/TOML) + schema helpers.
- `tests/` – unit/integration tests mirroring the above structure.

If you must introduce a new area of core logic, put it under `openwrt_imagegen/` and update `ARCHITECTURE.md` if you deviate from this structure.

## 4. Database, profiles, and builds

- Treat the **database + ORM as the source of truth** for:
  - Profiles.
  - Image Builder variants.
  - Build records and artifact metadata.
- Profiles:
  - Are not mutated during builds; to change behavior, create a new profile or pass explicit options.
  - Should be queryable by stable ID, release, target, tags, etc.
  - May have import/export helpers under `profiles/` but runtime logic should read from the ORM.
- Build records:
  - Must link to both a profile and an Image Builder record.
  - Include all inputs (extra packages, overlays, flags) and outputs (paths, checksums, logs).
  - Power cache decisions (build‑or‑reuse vs force rebuild).

When adding/adjusting models or queries, mirror the responsibilities and queries described in `ARCHITECTURE.md` and `AI_CONTRIBUTING.md`.

## 5. TF/SD card flashing rules

Any code that touches block devices must follow these non‑negotiable rules (see `ARCHITECTURE.md` + `AI_CONTRIBUTING.md` for detail):

- Operate on explicit **whole‑device paths only** (e.g. `/dev/sdX`, never `/dev/sdX1`).
- Never guess devices; require the caller to provide the path and use explicit `--force` or similar for destructive actions.
- Perform pre‑flight checks (block device detection; optional signature wipe/zero‑fill when requested).
- Write synchronously and flush caches (equivalent to `dd ... conv=fsync` + `sync`).
- Verify writes with hash comparison of image vs device (full image or well‑documented prefix).
- Log operations in detail and surface errors clearly; treat hash mismatches as failures.

If a proposed change makes flashing less safe or less observable, do not make that change.

## 6. Frontend behavior (CLI, web, MCP)

- Keep all three frontends **thin**:
  - CLI: argument parsing, calling core functions, printing text/JSON, clear exit codes.
  - Web: HTTP routing + auth/validation + mapping to core APIs.
  - MCP: idempotent, cache‑aware operations that map 1:1 to core APIs and return structured metadata.
- Do not add build/flash logic directly into CLI commands, HTTP handlers, or MCP handlers.

When extending a workflow, first add/extend a core function under `openwrt_imagegen/`, then wire it through the relevant frontend.

## 7. Testing & workflows

- Non‑trivial changes to core logic should come with or update tests under `tests/` (e.g. `pytest`).
- Core scenarios to cover:
  - Profile validation and lookup.
  - Image Builder selection/caching.
  - Build record creation and cache hit detection.
  - Flashing logic with mocked block devices and checksum verification.
- Tests must not depend on real TF cards or the network; use mocking/fakes around Image Builder and devices.

For examples of intended behavior and queries, rely on the narrative in `ARCHITECTURE.md` and rules in `AI_CONTRIBUTING.md` when designing tests.

## 8. How AI agents should operate

- Before writing new functionality, skim `README.md`, `ARCHITECTURE.md`, and `AI_CONTRIBUTING.md` to align with the existing design.
- Prefer:
  - Extending the core library first.
  - Adding/adjusting tests.
  - Keeping frontends as thin wiring layers.
- When naming things or structuring directories, favor explicit, reproducible patterns (e.g. `device_id/release/build-<timestamp>` for output trees) over opaque IDs.
- If documentation and code disagree, treat the **current code** as authoritative and update docs (including this file) to match.

When unsure, default to reproducibility, safety (especially for TF/SD flashing), and thin, well‑typed Python APIs.
