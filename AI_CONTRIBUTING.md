# AI Contribution Instructions

This document tells AI agents **how to work in this repository**: what is allowed, what is off-limits, and where to put new code. It summarizes and operationalizes the design in [ARCHITECTURE.md](ARCHITECTURE.md).

If you are an AI making changes here, follow this as a hard contract.

---

## 1. Core intent (what this repo is for)

- Provide an **AI-friendly orchestration layer** around the official OpenWrt Image Builder.
- Manage **profiles, builds, and artifacts in a database via an ORM**.
- Build and **safely flash** OpenWrt images to TF/SD cards for multiple devices.
- Offer **three frontends** over the same Python core:
  - CLI
  - Web interface
  - MCP server

This repo is _not_ trying to replace the OpenWrt SDK/buildroot or be a general OpenWrt toolkit.

If a change conflicts with this intent, **don’t do it**.

---

## 2. Golden rules for AI changes

1. **Do not re‑implement OpenWrt.**  
   Always shell out to the official OpenWrt Image Builder for firmware builds.

2. **Database + ORM are the source of truth.**

   - Profiles, Image Builder metadata, build records, and artifact tracking **must** be modeled in the database via an ORM.
   - YAML/JSON/TOML files are for **import/export/backup**, not primary storage.

3. **Profiles are immutable inputs.**

   - Never mutate profile objects during a build.
   - To change behavior, create a new profile or pass explicit options.

4. **Frontends are thin.**

   - CLI, web, MCP must:
     - Parse/validate input.
     - Call core Python APIs.
     - Format output.
   - They must **not** contain build/flash logic themselves.

5. **TF card flashing must be safe and verifiable.**

   - Never guess devices.
   - Only operate on explicit device paths.
   - Always log and verify.

6. **Prefer explicit over magic.**
   - No hidden global flags that change behavior unpredictably.
   - APIs should take clear, typed arguments.

Before writing code or docs that affect behavior, cross‑check with [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 3. Where AI should put new code

Follow the structure in `ARCHITECTURE.md`:

- `openwrt_imagegen/`
  - `imagebuilder/` – Image Builder fetch/cache logic and DB metadata.
  - `profiles/` – ORM models and APIs for profile management.
  - `builds/` – build orchestration, build records, artifact & cache tracking.
  - `flash/` – TF/SD card flashing workflows and safety checks.
  - `cli.py` / `__main__.py` – thin CLI wrapper.
- `web/` – web UI over the same APIs (thin layer).
- `mcp_server/` – MCP server calling the same APIs (thin layer).
- `profiles/` – optional import/export formats and schema helpers.
- `docs/` – documentation (`ARCHITECTURE.md`, `PROFILES.md`, etc.).
- `tests/` – unit/integration tests mirroring the package layout.

**Do not** introduce new top‑level packages or folders for core logic unless you also update `ARCHITECTURE.md` accordingly.

---

## 4. Data & database rules

### 4.1 Profiles

- Must be represented as ORM models in `openwrt_imagegen/profiles/`.
- Must include at least:
  - Stable ID / device identifier.
  - OpenWrt release, target, subtarget.
  - Image Builder profile name.
  - Package lists.
  - Overlay / config references.
- Access patterns:
  - Prefer queries that filter on ID, release, target, tags.
  - Changes are done via explicit CRUD operations, not implicit mutation in build flows.
- Fallback behavior:
  - The code should handle an **uninitialized DB** in CLI mode by:
    - Either initializing a default SQLite DB, **or**
    - Using a small in‑memory/temporary profile set for simple commands.
  - Document any such behavior in code comments.

### 4.2 Image Builder metadata

- Model: in `openwrt_imagegen/imagebuilder/` as an ORM entity (e.g. `ImageBuilder`).
- Store:
  - `release`, `target`, `subtarget`.
  - Upstream download URL.
  - Local archive/root paths.
  - Checksums.
  - Status (available, missing, failed, retired).
  - Lifecycle info (support/EOL, local deprecation).
  - Usage timestamps.
- Build records must **reference** Image Builders by foreign key.

### 4.3 Build records and artifacts

- Model in `openwrt_imagegen/builds/` via ORM.
- Must capture:
  - Profile reference.
  - Image Builder reference.
  - Options (extra packages, overlays, flags).
  - Output paths (images, checksums, logs).
  - Result (success/failure) and error details.
  - Timestamps.
- Image cache semantics:
  - The DB decides whether a cache hit exists for a given set of inputs.
  - The API should support both:
    - “build‑or‑reuse” (idempotent default).
    - “force rebuild”.

When in doubt, design schemas to support the queries described in `ARCHITECTURE.md` (e.g. “latest successful build for profile X”).

---

## 5. TF card flashing rules for AI

Changes touching TF/SD card flashing **must** follow these rules:

1. **Whole-device only.**

   - Always operate on paths like `/dev/sdX`, **never** `/dev/sdX1` etc.

2. **No device guessing.**

   - Require the caller to specify the device path.
   - Do not auto‑select based on size, labels, or guesses.

3. **Pre‑flight checks and optional wipe.**

   - Validate that the path is a block device.
   - Optionally:
     - Clear signatures/partition tables (like `wipefs`).
     - Zero-fill when explicitly requested.

4. **Synchronous, flushed writes.**

   - Equivalent behavior to `dd ... conv=fsync` followed by `sync`:
     - Do not mark the operation as complete until OS/device caches are flushed.

5. **Hash-based verification.**

   - Read back from the device after writing.
   - Compare hashes of:
     - The full image, or
     - A well‑documented prefix (e.g. first 16–64 MiB).
   - Treat mismatched hashes as a failure.

6. **Ghost‑write / bad‑card detection.**

   - If writes appear to succeed but read‑back doesn’t match:
     - Log clearly.
     - Optionally record the device as “suspect/unhealthy” in DB or logs.

7. **Post‑boot validation hooks.**

   - Build process should support embedding:
     - A build ID file (e.g. `/etc/build-id`).
     - Or a banner marker.
   - Flash module doesn’t read it, but should:
     - Expose enough metadata so frontends can tell users how to verify after boot.

8. **Dry run and force.**
   - Provide a dry‑run mode that:
     - Shows exactly what would be done (device, image, size, wipes).
   - Use explicit `--force` or equivalent for destructive paths.

If any change weakens these safety guarantees, do not make it.

---

## 6. Frontend guidelines (CLI, web, MCP)

### CLI

- Only performs:
  - Argument parsing & validation.
  - Calling **core Python APIs**.
  - Rendering text/JSON output.
- Must support:
  - Non‑interactive usage for CI.
  - JSON (or similar) structured output for tools/AI.
  - Clear exit codes (0 success, non‑zero with meaning).

### Web interface

- Thin layer over the same APIs.
- Each UI action:
  - Should correspond to one core function (e.g. `build_or_reuse_image(profile_id, options)`).
- No business logic inside HTTP handlers beyond auth/validation.

### MCP server

- Creates well‑scoped, idempotent operations:
  - E.g., “build‑or‑reuse image for profile X with options Y”.
- Must return:
  - IDs.
  - Paths.
  - Statuses needed for orchestration.
- Never implement build/flash logic inside MCP handlers; always call core APIs.

---

## 7. Testing expectations for AI changes

Every non‑trivial change should include or update tests in `tests/`:

- For core logic:
  - Unit tests for:
    - Profile validation.
    - Image Builder selection and caching.
    - Build record and cache key computation.
    - TF card flashing logic (mocked devices).
- For DB models:
  - Tests that:
    - Create/read/update/delete profiles, builders, builds.
    - Exercise common queries described in the architecture.

Tests should be runnable with a single command (e.g. `pytest`) and should not require real TF cards or real network access.

---

## 8. When in doubt

If you’re an AI agent and you’re unsure:

- Prefer:
  - Adding or updating **core library APIs** in `openwrt_imagegen/` + tests.
  - Minimal changes to CLI/web/MCP just to wire through new functionality.
- Re-read:
  - `README.md` for high-level intent.
  - `ARCHITECTURE.md` for authoritative details.

Never introduce new cross‑cutting patterns (configuration style, logging framework, DB layer) without aligning them with the existing architecture.
