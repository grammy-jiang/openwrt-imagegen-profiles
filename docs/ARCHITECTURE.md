# Architecture Overview

This repository defines an AI-friendly toolchain for building and managing custom OpenWrt firmware images across multiple devices. It combines (see also [README.md](../README.md)):

- **Declarative device profiles** – version-controlled descriptions of how each device’s image should be built.
- **A Python orchestration core** – responsible for dynamically fetching and caching the official OpenWrt Image Builder, running reproducible builds, tracking artifacts, and coordinating flash workflows.
- **Multiple frontends over the same logic**:
  - A **CLI** for local and CI usage.
  - A **web interface** for interactive use.
  - An **MCP server** so other AI tools and services can drive builds programmatically.

The goal is to make it easy for both humans and AI agents to request reproducible OpenWrt images on demand, re-use previous results via caching, and safely write them to TF cards, all through a single, well-defined set of APIs.

---

## Glossary

- **Profile** \
  A declarative description of how to build an OpenWrt image for a specific device. Includes device ID, OpenWrt release, target/subtarget, Image Builder profile name, package set, and optional overlays or policies. Treated as immutable input to builds and persisted in a database (with optional export/import to version-controlled data files).

- **OpenWrt Image Builder** \
  The official OpenWrt toolchain for assembling firmware images from prebuilt packages. This project always shells out to the official Image Builder instead of re-implementing build logic.

- **Image Builder cache** \
  A local directory tree where downloaded and extracted Image Builder archives are stored, keyed by release and target/subtarget so they can be reused across multiple builds.

- **Image build library** \
  The Python module(s) that construct Image Builder commands, run builds, collect outputs, maintain build records, and implement the image cache.

- **Build record** \
  A structured representation of one build execution, capturing inputs (profile, release, options), outputs (image paths, checksums, logs), timestamps, and result status.

- **TF card flashing module** \
  Python code responsible for writing selected images to explicit block devices (TF cards), with dry-run, verification, and detailed logging.

- **Frontend** \
  Any user- or tool-facing layer—CLI, web UI, MCP server, or other automation—that calls into the shared orchestration core without duplicating business logic.

---

## Core package design

`openwrt_imagegen/` is the single Python package. Subpackages and their responsibilities:

- `openwrt_imagegen/imagebuilder/`

  - Discover official Image Builder URLs for `(release, target, subtarget)`.
  - Download/verify archives, extract to cache roots, record metadata, and manage cache pruning (see [BUILD_PIPELINE.md](BUILD_PIPELINE.md)).
  - Expose “ensure builder present” and cache state/query APIs.
  - Key components:
    - `models.py`: ORM `ImageBuilder` model (release, target, subtarget, urls, checksums, state, paths, timestamps).
    - `fetch.py`: URL discovery, download with checksum/signature verification, extraction, pruning helpers.
    - `service.py`: high-level functions `ensure_builder(...)`, `list_builders(...)`, `prune_builders(...)`, with locking.

- `openwrt_imagegen/profiles/`

  - ORM models for profiles; validation and import/export (YAML/JSON/TOML).
  - Query APIs (by `profile_id`, tag, release, target/subtarget).
  - Profile CRUD (when enabled) with history/version-awareness where applicable.
  - Key components:
    - `models.py`: ORM `Profile` model.
    - `schema.py`: Pydantic models for on-disk schema, validation.
    - `io.py`: import/export helpers for YAML/JSON/TOML with validation and reporting.
    - `service.py`: CRUD/query APIs, tag/filter search, batch selection resolution.

- `openwrt_imagegen/builds/`

  - Build orchestration: cache-key computation, overlay staging, calling Image Builder, artifact discovery, manifest generation.
  - BuildRecord and Artifact ORM models; cache lookup and cache-hit handling.
  - Batch build orchestration (multi-profile) with per-profile results.
  - Concurrency controls and locking for builders and cache keys.
  - Key components:
    - `models.py`: ORM `BuildRecord`, `Artifact`, optional `BatchBuild`.
    - `cache_key.py`: canonical input snapshot and hash computation (profiles, packages, overlays hash, builder, options).
    - `overlay.py`: staging of FILES tree, hashing of staged content.
    - `runner.py`: compose and execute Image Builder commands; capture logs.
    - `artifacts.py`: discover outputs, classify kinds, hash, and write manifest.
    - `service.py`: high-level `build_or_reuse(...)`, `build_batch(...)`, `list_builds(...)`, with locking and concurrency limits.

- `openwrt_imagegen/flash/`

  - Flash workflows adhering to [SAFETY.md](SAFETY.md): device validation, optional wipe, write, hash verification, logging.
  - Optional FlashRecord model for audit trails.
  - Key components:
    - `models.py`: optional ORM `FlashRecord`.
    - `device.py`: validation of block devices (whole-device only), optional metadata via pyudev.
    - `writer.py`: wipe (when requested), write with fsync, hash verification (full/prefix).
    - `service.py`: high-level `flash_artifact(...)` / `flash_image(...)` with dry-run and force flags.

- `openwrt_imagegen/config.py`

  - Config/env parsing (pydantic), defaults for paths (cache/artifacts/DB/tmp), and feature toggles (offline mode, concurrency limits).
  - Expose a single `Settings` object and helper to render effective config as JSON.

- `openwrt_imagegen/__main__.py` or `cli.py`

  - Thin CLI that delegates to the above modules; argument parsing only.

- `web/`

  - FastAPI app exposing HTTP endpoints that proxy to `openwrt_imagegen` APIs.

- `mcp_server/`
  - FastMCP-based MCP server implementing tools described in [FRONTENDS.md](FRONTENDS.md).

All shared types (e.g., dataclasses for request/response payloads) should live in a small `openwrt_imagegen/types.py` or equivalent to avoid cycles.

---

## Execution contexts and flows

- **CLI**: synchronous calls into core modules; supports JSON output for automation; long-running operations should emit status and return build/flash IDs for polling.
- **Web**: HTTP endpoints that start builds/flash operations and return IDs; clients poll for status/logs; optional SSE/WebSocket can reuse the same payloads.
- **MCP**: idempotent tool calls mapping to core APIs; must surface cache hits, errors with codes, and log paths; batch builds supported.
- **Automation/CI**: invoke CLI or MCP with JSON outputs; rely on stable exit codes defined in [OPERATIONS.md](OPERATIONS.md).

Data flow (build request):

1. Resolve profile(s) (DB + validation).
2. Ensure Image Builder present (download/verify/cache).
3. Compute cache key (profile snapshot + overlays hash + options).
4. Lock on cache key; check for existing successful build.
5. Stage overlays (`FILES`), compose `make image` command, run.
6. Discover artifacts, compute hashes, write manifest, persist records.
7. Return structured result (status, cache_hit, artifacts, log path).

Data flow (flash request):

1. Resolve artifact (by ID or path) and checksum.
2. Validate device path (whole-device only).
3. Optional wipe; write with fsync; verify hash (full or prefix).
4. Log and persist flash record (if model exists); return status and log path.

Sequence (batch build request):

1. Resolve profile set (explicit list or filter) and persist the resolved list.
2. For each profile: ensure builder, compute cache key, acquire lock.
3. Reuse cached builds when present; queue new builds respecting concurrency limits.
4. Aggregate per-profile results (status, cache_hit, artifacts, log path) and batch status (fail-fast vs best-effort).

---

## State and storage

- **Database**: ORM-backed tables for profiles, ImageBuilders, BuildRecords, Artifacts, and optional FlashRecords (see [DB_MODELS.md](DB_MODELS.md)). SQLite by default; Postgres supported via `psycopg` when configured.
- **Filesystem**:
  - Image Builder cache: `~/.cache/openwrt-imagegen/builders/<release>/<target>/<subtarget>/`
  - Build working dirs: `<cache_root>/<release>/<target>/<subtarget>/builds/<profile>/<build_id>/`
  - Artifacts: `~/.local/share/openwrt-imagegen/artifacts/<release>/<target>/<subtarget>/<profile_id>/<build_id>/`
  - Logs: user-owned log dir with rotation (documented in [OPERATIONS.md](OPERATIONS.md)).
  - Overlays staging: temp dir per build; staged tree hashed and referenced via `FILES=`.

---

## Configuration and precedence

- Sources: CLI flags > environment variables > config file (if added) > defaults (see [DEVELOPMENT.md](DEVELOPMENT.md)).
- Key knobs: cache/artifacts/db paths, offline mode, concurrency limits (builders/builds), timeout limits for downloads/builds/flashes, verification mode (full vs prefix), fail-fast vs best-effort for batch builds.
- Config parsing via pydantic; expose effective config in JSON for observability.

---

## Concurrency, locking, and queues

- Per-builder locks for downloads `(release, target, subtarget)`.
- Per-cache-key locks for builds; waiters consume the finished build as cache hits.
- Configurable concurrency limits for build execution to avoid resource contention; queue additional requests FIFO.
- Batch builds should respect the same locks/limits while iterating over profiles.

---

## Observability and error semantics

- Logging: stdlib `logging` with structured context (profile_id, build_id, imagebuilder release/target/subtarget, cache_key, artifact_id, device).
- Errors: typed exceptions with stable codes (see [OPERATIONS.md](OPERATIONS.md)); surface in CLI/web/MCP outputs with `code`, `message`, `log_path`.
- Manifests: each build writes a manifest (JSON) containing inputs, artifacts, hashes, and cache key to aid debugging and reuse.
- Metrics (optional): add hooks for counters/timers (downloads, cache hits/misses, build duration, flash verification failures) if/when a metrics backend is chosen.
- Tracing/logging consistency: include request IDs in web/MCP surfaces and propagate through core calls for correlation.

---

## Extensibility guidelines

- Add new profile fields only with matching validation and DB schema updates; document in [PROFILES.md](PROFILES.md) and [DB_MODELS.md](DB_MODELS.md).
- New CLI/web/MCP features must call into core modules; do not reimplement build/flash logic.
- Keep batch operations and idempotency in mind for new APIs; prefer deterministic inputs and cache-aware behavior.
- Maintain backward-compatible JSON shapes for CLI/MCP/web; add fields compatibly and deprecate before removal.

---

## Core Responsibilities

The system focuses on four main responsibilities. Each responsibility is implemented in a way that is:

- **AI-friendly** – clear inputs/outputs, minimal hidden state.
- **Idempotent where possible** – safe to call repeatedly from automation and MCP tools.
- **Composable** – higher-level flows ("build and flash this device") are just orchestration over these primitives.

### 1. Dynamic OpenWrt Image Builder management

This responsibility ensures the correct official Image Builder is always available without requiring the user to manage archives manually.

- Given a requested OpenWrt **release**, **target**, and **subtarget**, the tool:
  - Locates the corresponding official **OpenWrt Image Builder** on the OpenWrt download servers.
  - Downloads it on demand (with progress and basic integrity checks where possible).
  - Extracts and **caches** it in a local store for re-use across future builds.
- The cache is keyed by:
  - OpenWrt release (e.g. `23.05.3`),
  - Target/subtarget (e.g. `ramips/mt7621`),
  - Architecture-specific details as needed.
- The module exposes explicit operations such as "ensure Image Builder present for (release, target, subtarget)" so frontends do not need to know download URLs.
- When a newer minor release or rebuild is requested, the system can maintain multiple cached builders side by side for full reproducibility.
- Metadata about each cached Image Builder (release, target/subtarget, upstream URL, local paths, checksum, status, usage timestamps) is stored in the database via the ORM. Build records reference these entries, making the database the source of truth for which Image Builder variants exist and where they live on disk.
- This avoids repeating large downloads, while always staying aligned with official upstream releases and making cache state observable to CLIs, web UIs, and MCP clients.

### 2. Profile management

Profile management provides a single source of truth for how each device should be built, backed by a database and accessed through an ORM, with reasonable behavior when the database is not yet initialized (see [PROFILES.md](PROFILES.md) and [DB_MODELS.md](DB_MODELS.md)).

- Each device is described by a **profile**, which acts as an immutable, declarative build recipe:
  - Device identifier (human-friendly ID).
  - OpenWrt release, target, subtarget, and Image Builder profile name.
  - Package set (base + custom).
  - Optional overlay files, configuration snippets, and policies.
- Profiles are:
  - Stored in a database (from SQLite in local setups to PostgreSQL or similar in multi-user/service deployments).
  - Accessed via an ORM layer in the Python code, so application logic is decoupled from the specific database engine.
  - Optionally exported/imported as version-controlled data files for backup, review, and migration.
  - Validated before use (schema checks, reference checks against known targets/profiles where possible).
  - Never mutated in place during builds; new behavior is derived from them.
  - Able to fall back to sensible defaults when the database is missing or not initialized (e.g. a small in-memory profile set or on-the-fly temporary definitions in CLI-only workflows).
- A profile management layer will support:
  - Listing and searching existing profiles by device ID, release, target, tags, or free text.
  - Creating, editing, cloning, and deprecating profiles.
  - Tracking profile history and allowing reproducible builds from older revisions (e.g. via versioned rows or history tables in the database).
  - Referencing profiles consistently from the CLI, web UI, and MCP server via stable identifiers.
- The goal is for an AI or human caller to specify "build this device profile" without worrying about low-level Image Builder flags.

### 3. Image build library and artifact tracking

The image build library is the heart of the system, turning profiles into concrete firmware images.

- The build library encapsulates all logic to:
  - Compose the appropriate Image Builder command from a given profile and options.
  - Run the build in a controlled environment with clear logging of stderr/stdout.
  - Collect resulting images and logs into a structured output tree (e.g. by device ID, release, timestamp/build ID).
- Every build produces a **build record** that includes:

  - Input profile (or a stable reference to it).
  - OpenWrt release and Image Builder variant used.
  - Build options (e.g. extra packages, overlay paths).
  - Output artifact paths (firmware images, checksums, logs).
  - Timestamps and outcome (success/failure, error messages).

Build records and artifact metadata are persisted in the database via the ORM, allowing queries such as "find the latest successful build for this profile", "list all builds that produced a given image", or "show all images for a given device and release".

- The library maintains an **image cache** backed by the database:
  - Before building, it checks whether an image with the same effective inputs already exists.
  - If found and valid, it returns the existing artifact instead of rebuilding.
  - This enables fast repeat builds and easy auditing: same inputs, same outputs.
- The public API is designed so that a caller can either:
  - Request "build-or-reuse" behavior (default for CLIs, web, MCP), or
  - Force a rebuild when explicitly needed (e.g. for debugging or testing).
- Build records and cache metadata are exposed in a way that frontends and external tools can query status, list past builds, and fetch artifacts programmatically, with the database as the source of truth.

### 4. TF card flashing (write workflows)

TF card flashing is modeled as a separate, safety-critical workflow layered on top of build results. It is designed to detect and avoid "ghost writes" where a new image appears to flash successfully but the device still boots an old system.

- A dedicated module coordinates safely writing built images to TF cards:
  - Takes an explicit image (or build ID) and an explicit block device path (e.g. `/dev/sdX`, never a partition like `/dev/sdX1`).
  - Logs what it will do before writing, including device, image, and size information.
  - Optionally wipes old signatures or zeroes the device (e.g. via `wipefs` or a zero-fill pass) before writing, to avoid stale partition tables and filesystems.
  - Performs the write in a way that flushes caches (equivalent to `conv=fsync` / `sync`) before the device is considered ready to remove.
  - Verifies the write by reading back data from the device and comparing hashes (full image or a configurable prefix) against the source image.
- Safety and correctness are prioritized:
  - No guessing or auto-selecting block devices.
  - No destructive actions without clear, explicit input (and ideally explicit "force" flags from automation).
  - Clear error messages when preconditions are not met (missing image, non-block device path, insufficient permissions, read-only media, etc.).
  - Ability to detect and flag suspicious behavior such as cards that appear to accept writes but read back old data, and to mark such devices as unhealthy in logs or metadata.
- Post-flash validation is supported where possible:
  - The flashing module can integrate with build metadata (e.g. a unique build ID file or banner embedded into the image) so that frontends can guide users to verify the running system after boot.
  - Workflows and logs make it easy to trace which image was written to which card and when.
- Over time, the module can be extended with optional device-lab features (e.g. tracking which TF card was flashed with which image, or managing card health status) while keeping the core write operation minimal, auditable, and reproducible.

---

## Frontends and Integration Surfaces

All user-facing interfaces are thin layers over the same Python orchestration core. They should not contain business logic beyond input validation, access control, and presentation.

### CLI

- Primary tool for developers and CI.
- Expected commands include, for example:
  - Managing profiles (list, show, create, update, clone).
  - Managing OpenWrt Image Builder cache (ensure, list, prune).
  - Building images (on-demand, or batch for multiple profiles).
  - Inspecting build history and cached images.
  - Writing images to TF cards with safety checks and dry-run support.
- Designed to be scriptable and deterministic for automation:
  - Stable, documented exit codes.
  - Structured output options (e.g. JSON) so other tools and AI agents can parse results reliably.
  - Support for non-interactive mode suitable for CI and MCP callers.

### Web interface

- Provides an interactive GUI on top of the same operations:
  - Select device profiles.
  - Trigger builds and view status/logs.
  - Browse cached images and build history.
  - Initiate TF card write workflows with clear warnings.
- Intended for local or controlled environments, not as a public Internet service.
- Built as a thin layer over the same Python APIs, so any UI action maps cleanly to an underlying library call (and therefore can be mirrored by CLI or MCP).

### MCP server

- Exposes the core capabilities to AI tools and external systems via the **Model Context Protocol**:
  - Query available profiles and releases.
  - Request image builds (with idempotent, cache-aware semantics).
  - Retrieve metadata and paths for built images.
  - Orchestrate TF card write operations (in controlled environments).
- The MCP layer does not re-implement business logic; it forwards requests into the same Python functions used by the CLI and web UI.
- Endpoints are designed to be:
  - **Idempotent** where possible (e.g. "build-or-reuse" operations keyed by profile + options).
  - **Observable** – returning enough metadata (IDs, paths, statuses) for higher-level orchestration.
  - **Defensive** – validating inputs to prevent unsafe operations, especially around TF card flashing.

---

## Design Principles

Several principles guide the overall design and should be preserved when extending the system:

### Reproducibility

- Profiles are immutable inputs.
- Builds are fully determined by profile + Image Builder version + explicit options.
- Build records and caches allow exact reconstruction of what was built, when, and from which inputs.
- Whenever behavior must change (e.g. new defaults, different package selections), prefer creating new profiles or explicit options rather than relying on global configuration.

### Separation of concerns

- Profiles: data only.
- Orchestration: Python library that:
  - Manages Image Builder downloads and caches.
  - Constructs and runs Image Builder calls.
  - Tracks build artifacts and history.
- Frontends (CLI, web, MCP): thin shells that parse input, call library functions, and format output.
- Service-specific concerns (authentication, authorization, rate limiting, etc.) should be kept out of the core library and implemented at the edge.

### Safety

- Image building itself is delegated to the official OpenWrt Image Builder; no re-implementation of low-level firmware logic.
- Any interaction with TF cards or block devices:
  - Requires explicit device paths.
  - Favors dry-run, confirmation, and verification.
  - Logs operations in detail.
- Error handling should be explicit and informative, preferring clear exceptions/messages over silent failures.
- AI-facing surfaces (MCP, structured CLI output) should expose enough detail for tools to make safe decisions (e.g. distinguish "image not found" from "device path invalid").

### AI-first ergonomics

- Clear, machine- and human-readable profiles and schemas.
- Well-defined, side-effect-aware Python APIs.
- Strong documentation of constraints and invariants, so AI-generated code can stay within safe, intended bounds.
- Operations that may be expensive or destructive (downloads, rebuilds, flashing) should have explicit flags or modes so AI agents can choose conservative defaults.

---

For a quick, human- and AI-oriented summary of the project purpose and outcomes, see [README.md](../README.md). For detailed component-level behavior and extension guidelines, this `ARCHITECTURE.md` is the primary reference. For the concrete profile schema and examples used by the profile management layer, see `PROFILES.md`.

---

## Expected Directory Layout

The exact package names may evolve, but the architecture assumes a layout along these lines:

- `profiles/` \
  Optional profile export/import definitions (e.g. YAML/JSON/TOML) and schema/validation helpers, used for backup, review, and migration rather than as the primary storage.

- `openwrt_imagegen/` (or similar package) \
  Core Python orchestration code:

  - `imagebuilder/` – fetch & cache logic for OpenWrt Image Builder.
  - `profiles/` – ORM models and APIs for profile loading, validation, and management.
  - `builds/` – image build library, ORM-backed artifact tracking, build records, image cache.
  - `flash/` – TF card flashing workflows and safety checks.
  - `cli.py` or `__main__.py` – thin CLI wrapper over the library.

- `web/` \
  Web application that provides an HTTP API (and optional GUI) backed by the same orchestration APIs.

- `mcp_server/` \
  MCP server implementation that exposes profile, build, and flash operations to external tools.

- `docs/` \
  Additional documentation such as `PROFILES.md`, `BUILD_PIPELINE.md`, `SAFETY.md`, and this `ARCHITECTURE.md`.

- `tests/` \
  Unit and integration tests for the core library and frontends, mirroring this layout where practical.

All OpenWrt- and build-related business logic should live under `openwrt_imagegen/`. Frontends (`cli.py`, `web/`, `mcp_server/`) should call these library functions rather than implementing their own build or flash flows.

This structure matches the current implementation and should be preserved when adding new functionality.

---

## TODO / coordination for AI onboarding

- Keep `../.github/copilot-instructions.md` in sync with this document whenever you:
  - Add real code under `openwrt_imagegen/`.
  - Introduce tests, CI workflows, or new frontends.
  - Change how builds, profiles, or flashing are wired.
- Treat `../.github/copilot-instructions.md` as the **entrypoint** for AI agents; update it in the same PR as any architectural change so future agents don’t need to rediscover the workflow or run failing commands.
