# FRONTENDS.md – CLI, web, and MCP frontends

This document describes the expected behavior and responsibilities of the
frontends for this project:

- **CLI** commands.
- **Web** interface.
- **MCP** server.

All frontends are thin layers over the same Python orchestration core, which
handles:

- Profile management (see [PROFILES.md](PROFILES.md) and [DB_MODELS.md](DB_MODELS.md)).
- Image Builder management and build orchestration (see [ARCHITECTURE.md](ARCHITECTURE.md) and [BUILD_PIPELINE.md](BUILD_PIPELINE.md)).
- TF/SD flashing workflows and safety (see [SAFETY.md](SAFETY.md)).

This file focuses on how frontends should call into those core APIs and how they
should present results.

---

## 1. Shared principles

Across all frontends:

1. **No business logic duplication**

   - Frontends must not implement their own build, cache, or flashing logic.
   - They only:
     - Parse and validate input.
     - Call core library functions.
     - Render responses (text, HTML, JSON, MCP tool outputs).

2. **Idempotent, cache-aware operations**

   - Frontends should expose operations like "build-or-reuse" (default) and
     "force rebuild" in a way that maps directly to the semantics in
     [BUILD_PIPELINE.md](BUILD_PIPELINE.md).

3. **Safety-first flashing**

   - Any action that writes to TF/SD cards uses the flashing APIs defined in
     `openwrt_imagegen/flash/` and honors all rules from [SAFETY.md](SAFETY.md).

4. **Structured, machine-readable outputs**

   - Wherever possible, frontends should offer JSON or similarly structured
     output so other tools and AI agents can consume results.

5. **Clear error reporting**

   - Errors should be:
     - Mapped from structured core exceptions to frontend-specific formats.
     - Descriptive enough for both humans and AI agents.

6. **Streaming and observability**

   - Prefer simple polling endpoints first (e.g., `GET /builds/{id}`, `GET /builds/{id}/log`) that return the same data shapes used by CLI/MCP.
   - Add SSE/WebSocket streaming only when justified; reuse the same payloads and error codes.
   - Surface cache-hit vs new-build, artifact metadata, and log paths consistently.

6. **Streaming and observability**

   - Prefer simple polling endpoints first (e.g., `GET /builds/{id}`, `GET /builds/{id}/log`) that return the same data shapes used by CLI/MCP.
   - Add SSE/WebSocket streaming only when justified; reuse the same payloads and error codes.
   - Surface cache-hit vs new-build, artifact metadata, and log paths consistently.

---

## 2. CLI frontend

The CLI is the primary tool for developers and CI pipelines.

### 2.1. Responsibilities

The CLI should:

- Provide commands for:

  - Profile management (list, show, create, update, export/import).
  - Image Builder cache management (ensure, list, prune).
  - Building images (build-or-reuse, force rebuild, batch builds).
  - Inspecting build history and artifacts.
  - Flashing TF/SD cards using existing artifacts.

- Support both human-friendly and machine-readable output formats.
- Offer clear exit codes suitable for CI.

### 2.2. Example command shapes

Examples of how CLI commands might map to core APIs (names are illustrative):

- Profiles:

  - `imagegen profiles list --tag lab --release 23.05.2`
  - `imagegen profiles show --profile-id home.ap-livingroom.23.05`
  - `imagegen profiles import profiles/home-ap-livingroom.yaml`
  - `imagegen profiles export --profile-id home.ap-livingroom.23.05 -o -`

- Builds:

  - `imagegen build --profile-id lab.router1.extended`
  - `imagegen build --profile-id lab.router1.extended --force-rebuild`
  - `imagegen builds list --profile-id lab.router1.extended --status succeeded`

- Artifacts:

  - `imagegen artifacts list --build-id 123`
  - `imagegen artifacts show --artifact-id 456`

- Flashing:
  - `imagegen flash --artifact-id 456 --device /dev/sdX --dry-run`
  - `imagegen flash --artifact-id 456 --device /dev/sdX --force`
- Batch builds:
  - `imagegen build --tag 23.05 --target ath79 --subtarget generic`
  - `imagegen build --profiles home.ap-livingroom.23.05 home.ap-bedroom.23.05`

### 2.3. Implementation notes

- Internally, the CLI should:

  - Use a modern argument-parsing library (e.g. Typer, Click, or argparse).
  - Map commands to calls into `openwrt_imagegen` modules:
    - `openwrt_imagegen.profiles` for profile operations.
    - `openwrt_imagegen.builds` for builds and artifacts.
    - `openwrt_imagegen.imagebuilder` for builder cache actions.
    - `openwrt_imagegen.flash` for flashing.

- JSON output mode:
  - Provide a `--json` flag or similar that returns structured responses
    consistent with MCP and web API schemas.

### 2.4. Behavior and outputs

- Exit codes map to error classes (see `OPERATIONS.md`) so CI can distinguish validation errors vs build failures vs flash failures.
- `--json` output should include stable keys: `status`, `cache_hit`, `artifacts`, `log_path`, and `error` (`code`, `message`, `details`).
- Long-running operations (build/flash/batch) should print periodic status or instruct users to poll a `build_id` / batch ID / `flash_id` rather than blocking silently.

---

## 3. Web frontend

The web interface provides a GUI on top of the same core APIs.

### 3.1. Responsibilities

The web UI should allow users to:

- Browse and search profiles.
- Edit or clone profiles (with appropriate validation and confirmation).
- Trigger builds and display their status and logs.
- List artifacts and download images.
- Trigger flashing workflows on controlled machines.
- Run batch builds filtered by tag/release/target and present per-profile results.

### 3.1.1. Web UX / API guidance

- Keep HTTP routes thin proxies to core APIs; prefer JSON-backed forms even for rendered pages so MCP/CLI can mirror the same payloads.
- Use POST to start long-running actions, then poll `GET /builds/{id}` / `GET /flash/{id}` for status and logs; add SSE/WebSocket only if needed later.
- Do not auto-select devices for flashing; require explicit input and confirmation flags mirroring CLI semantics (`--dry-run`, `--force`).

### 3.2. API design

- The web backend should expose HTTP APIs that:

  - Mirror the core operations:
    - `GET /profiles`, `GET /profiles/{id}`, `POST /profiles`, `PUT /profiles/{id}`.
    - `POST /builds` to request a build-or-reuse.
    - `GET /builds/{id}` for status and metadata.
    - `GET /builds/{id}/artifacts`.
    - `POST /builds/batch` to request builds by filter or explicit profile list.
    - `POST /flash` to request a flash operation.
  - Return JSON responses that include:
    - IDs, statuses, timestamps.
    - Profile, ImageBuilder, and BuildRecord references.
    - Artifact metadata (paths, sizes, hashes).
    - For batch builds: per-profile results (build_id, status, cache_hit, artifacts, log_path) plus overall batch status.

- The web UI should call these APIs instead of embedding business logic in
  templates or view functions.

### 3.3. Auth and deployment

- Authentication and authorization are out of scope for this document, but:
  - Web endpoints that can flash devices must be protected and likely limited to
    trusted environments.
  - The same flashing safety rules from `SAFETY.md` apply regardless of auth.

### 3.4. Web UX / API guidance

- Keep HTTP routes thin proxies to core APIs; prefer JSON-backed forms even for rendered pages so MCP/CLI can mirror the same payloads.
- Use POST to start long-running actions, then poll `GET /builds/{id}` / `GET /flash/{id}` / `GET /builds/batch/{id}` for status and logs; add SSE/WebSocket only if needed later.
- Do not auto-select devices for flashing; require explicit input and confirmation flags mirroring CLI semantics (`--dry-run`, `--force`).

---

## 4. MCP server

The MCP server exposes project capabilities to other AI tools via the
Model Context Protocol.

### 4.1. Responsibilities

- Define MCP tools such as:

  - `list_profiles`
  - `get_profile`
  - `build_image`
  - `build_images_batch`
  - `list_builds`
  - `list_artifacts`
  - `flash_artifact`

### 4.1.1. MCP behavior details

- Tools must be idempotent where applicable: `build_image` returns cache hits transparently unless `force_rebuild` is set; `flash_artifact` refuses to guess devices.
- Batch tool (`build_images_batch`) should accept filters or explicit profile lists, return per-profile build IDs/statuses/cache-hit flags, and support fail-fast vs best-effort modes (see `BUILD_PIPELINE.md`).
- Errors include a stable `code`, `message`, and `log_path` when available (see `OPERATIONS.md`).
- Streaming build/flash status can be handled by polling; if streaming is added, reuse the same payload shapes as `list_*`/`get_*`.

- Provide structured, machine-friendly results that include:
  - Stable IDs (profile IDs, build IDs, artifact IDs).
  - Paths or URLs for artifacts.
  - Status fields suitable for polling and orchestration.

### 4.2. Behavior and mapping

- MCP tools must:

  - Call the same core Python APIs that the CLI and web backend use.
  - Support idempotent build-or-reuse behavior, as outlined in
    `BUILD_PIPELINE.md`.

- Example mappings:

  - `build_image` MCP tool → `openwrt_imagegen.builds.build_or_reuse(...)`.
  - `build_images_batch` MCP tool → `openwrt_imagegen.builds.build_batch(...)`.
  - `flash_artifact` MCP tool → `openwrt_imagegen.flash.flash_artifact(...)`.

- Error handling:
  - Map internal exceptions to MCP error codes/messages.
  - Preserve enough structure that AI callers can distinguish between
    validation errors, missing resources, and operational failures (e.g.
    build timeouts, flash verification failures).

---

## 5. Consistency with core docs

- `ARCHITECTURE.md` defines frontends as thin layers over the core library;
  this file elaborates that contract.
- `BUILD_PIPELINE.md` describes how builds and artifacts behave; frontends must
  not diverge from that behavior.
- `SAFETY.md` describes flashing rules; frontends must present options and
  defaults that honor those rules.
- `DB_MODELS.md` defines the ORM model concepts; frontends should rely on those
  shapes for their API schemas.
- `AI_CONTRIBUTING.md` and `../.github/copilot-instructions.md` emphasize:
  - No reimplementation of build/flash logic in frontends.
  - Database + ORM as the source of truth.

This document should be updated if new frontends are added or if the behavior of
existing ones changes in a way that affects their responsibilities.
