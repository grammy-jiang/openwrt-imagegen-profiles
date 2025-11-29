# Web GUI Frontend Design

This document defines the functional and technical design of the web GUI for
`openwrt-imagegen-profiles`. It focuses on features, data flow, and endpoints,
not on visual styling.

The GUI is a thin HTML layer on top of the existing FastAPI web API and core
library. It is intended for local or trusted environments.

---

## 1. Goals and constraints

### 1.1. Goals

The web GUI should:

- Provide a human-friendly way to:
  - Browse and filter profiles.
  - Trigger and inspect builds.
  - Inspect artifacts produced by builds.
  - Run safe TF/SD flash workflows.
- Reuse the existing FastAPI web API and `openwrt_imagegen` services.
- Be simple to maintain, with minimal dependencies and no extra build tooling.

### 1.2. Constraints

- No SPA / heavy frontend frameworks:
  - No React/Vue/Svelte.
  - No Webpack/Vite/etc.
- Rendering: Jinja2 templates only.
- Routing: FastAPI `APIRouter` for HTML endpoints.
- Static assets: one small CSS file, one small JS file.
- No duplicated business logic:
  - GUI routes must call into JSON API routers in `web/routers` or
    core `openwrt_imagegen` services.
- Safety for flashing:
  - Do not auto-detect or guess block devices.
  - `dry_run` is the default.
  - Real writes require explicit user confirmation.

The GUI will live under the URL prefix:

- `/ui`

---

## 2. Backend structure

### 2.1. Python modules

New/extended modules under `web/`:

- `web/app.py`
  - Existing FastAPI app, extended to include the GUI router.
- `web/routers/gui.py`
  - New `APIRouter` containing all HTML endpoints under `/ui`.
- `web/deps.py`
  - Existing DI helpers: DB session, settings, etc.
- `web/templates/`
  - Jinja2 templates for the GUI.
- `web/static/`
  - Static CSS and JS files for the GUI.

Expected layout:

```text
web/
  app.py
  deps.py
  routers/
    __init__.py
    builders.py
    builds.py
    config.py
    flash.py
    health.py
    profiles.py
    gui.py             # NEW: HTML GUI routes
  templates/
    base.html
    dashboard.html
    profiles/
      list.html
      detail.html
    builds/
      list.html
      detail.html
    flash/
      list.html
      wizard.html
      detail.html
  static/
    css/
      style.css
    js/
      app.js
```

### 2.2. Router registration

In `web/app.py`:

- Import the GUI router:

  ```python
  from web.routers import gui
  ```

- Register it under `/ui`:

  ```python
  app.include_router(gui.router, prefix="/ui", tags=["gui"])
  ```

All GUI routes will then be available at `/ui/...`.

### 2.3. How GUI routes call backend logic

GUI handlers should **prefer calling core `openwrt_imagegen` services
directly** (via shared dependencies like `get_db_session` and
`get_settings`) rather than HTTP-calling the JSON endpoints. The JSON routers
and GUI therefore remain thin, parallel adapters over the same underlying
service functions.

---

## 3. Route map

The GUI exposes the following HTML endpoints:

- `GET /ui/` – Dashboard.
- `GET /ui/profiles` – List profiles.
- `GET /ui/profiles/{profile_id}` – Profile detail.
- `POST /ui/builds` – Trigger a build from a profile.
- `GET /ui/builds` – List builds.
- `GET /ui/builds/{build_id}` – Build detail + artifacts.
- `GET /ui/flash` – List flash operations.
- `GET /ui/flash/new` – Flash wizard (optional `artifact_id` query).
- `POST /ui/flash` – Start a flash.
- `GET /ui/flash/{flash_id}` – Flash detail.

Optional/advanced:

- `GET /ui/builds/{build_id}/status-fragment` – HTML snippet for build status polling.
- `GET /ui/profiles/new`, `POST /ui/profiles` – Profile create.
- `GET /ui/profiles/{profile_id}/edit`, `POST /ui/profiles/{profile_id}` – Profile edit.
- `GET /ui/builds/batch`, `POST /ui/builds/batch` – Batch builds.

---

## 4. Page-level design

Each page below describes:

- Purpose.
- Inputs.
- User actions.
- Backend behavior (which services/APIs are used).

The sections also call out how pages are linked together to support a
complete, reasonable workflow for common tasks such as
"build image → inspect artifacts → flash TF/SD card".

### 4.1. Dashboard – `GET /ui/`

**Purpose**

- Entry point for human operators.
- Show quick navigation and basic configuration.

**Inputs**

- None.

**User actions**

- Navigate to:
  - Profiles: `/ui/profiles`
  - Builds: `/ui/builds`
  - Flash: `/ui/flash`

**Backend behavior**

- Fetch settings via `get_settings()` from `web.deps` to display:
  - Cache dir.
  - Artifacts dir.
  - Database URL/path (masked if needed).
  - Offline mode flag.

Rendered template: `dashboard.html`.

**Role in end-to-end flows**

- Starting point for all user journeys.
- For "write image to TF card", the expected path is:
  - `/ui/` → `/ui/profiles` (choose profile) → profile detail → trigger build
    → build detail → choose artifact → flash wizard → flash detail.

---

### 4.2. Profiles

#### 4.2.1. Profiles list – `GET /ui/profiles`

**Purpose**

- Show available profiles with basic filtering.

**Inputs (query parameters)**

- `q` – free-text search (optional).
- `release` – OpenWrt release (optional).
- `target` – target (optional).
- `subtarget` – subtarget (optional).
- `tag` – repeated parameter for tags (optional).

**User actions**

- Adjust filters and submit.
- Click a profile ID to view its detail page.

**Backend behavior**

- Use `get_db_session()` from `web.deps`.
- Call `profiles_service.list_profiles` with filters.
- Render `profiles/list.html` with:
  - `profiles` – list of profiles.
  - `filters` – echo of applied filters.

**Role in end-to-end flows**

- Primary entry to select **which device/profile** you are working with.
- For "write image to TF card", the user:
  - arrives here from the dashboard,
  - locates the appropriate profile,
  - follows the link to `/ui/profiles/{profile_id}`.

#### 4.2.2. Profile detail – `GET /ui/profiles/{profile_id}`

**Purpose**

- Show details for a profile.
- Provide a small "Build this profile" form.
- Show recent builds for this profile.

**Inputs**

- `profile_id` path parameter.

**User actions**

- Inspect:
  - OpenWrt release.
  - Target/subtarget.
  - Image Builder profile name.
  - Package lists (base, extras, removed).
  - Overlay information.
  - Tags and metadata.
- Trigger a new build via the embedded form.
- Click recent builds to open their detail pages.

**Backend behavior**

- `profiles_service.get_profile(db, profile_id)`.
- `builds_service.list_builds(db, profile_id=..., limit=10)`.

Rendered template: `profiles/detail.html`.

The build form on this page posts to `POST /ui/builds`.

**Role in end-to-end flows**

- Represents the **"what to build"** decision for a single device/profile.
- For "write image to TF card":
  1. User reviews that this is the correct profile (release/target/packages).
  2. User triggers a build via the form (or reuses an existing build from the
     Recent builds section).
  3. User is redirected to `/ui/builds/{build_id}` once the build is
     requested.

---

### 4.3. Builds

#### 4.3.1. Trigger build – `POST /ui/builds`

**Purpose**

- Start a build-or-reuse operation for a profile.

**Inputs (form fields)**

- `profile_id` – profile identifier (required).
- `extra_packages` – string; space- or comma-separated packages (optional).
- `remove_packages` – string; space- or comma-separated packages (optional).
- `extra_image_name` – optional image name (optional).
- `force_rebuild` – boolean checkbox (optional).

**User actions**

- Submit from the profile detail page.
- On success, follow redirect to `/ui/builds/{id}`.

**Backend behavior**

- Parse and normalize packages into lists.
- Call:

  ```python
  builds_service.build_or_reuse(
      db=db,
      profile_id=profile_id,
      extra_packages=extras,
      remove_packages=removes,
      extra_image_name=extra_image_name,
      force_rebuild=force_rebuild,
  )
  ```

- On success: redirect (`303`) to `/ui/builds/{build.id}`.
- On error: re-render `profiles/detail.html` with:
  - the original profile,
  - recent builds,
  - an `error` message.

**Role in end-to-end flows**

- Bridges **profile selection** and **build inspection**:
  - Always returns the user to a build-centric page (`/ui/builds/{id}`).
- For "write image to TF card":
  - This is the moment where the build-or-reuse decision happens.
  - The following step is to inspect the resulting build in
    `/ui/builds/{build_id}`.

#### 4.3.2. Builds list – `GET /ui/builds`

**Purpose**

- Overview of builds across all profiles.

**Inputs (query parameters)**

- `profile_id` – filter to single profile (optional).
- `status` – `succeeded|failed|running|pending` (optional).

**User actions**

- Filter builds by profile/status.
- Click a build ID to open its detail page.

**Backend behavior**

- `builds_service.list_builds(db, profile_id=..., status=...)`.
- Render `builds/list.html` with:
  - `builds` – list of build records.
  - `filters` – applied filter values.

**Role in end-to-end flows**

- Alternative starting point when the desired image has already been built.
- For "write image to TF card":
  - Experienced users may skip profile pages, go directly to `/ui/builds`,
    filter by profile/status, and jump into the relevant build.

#### 4.3.3. Build detail – `GET /ui/builds/{build_id}`

**Purpose**

- Inspect status, artifacts, and logs for a build.

**Inputs**

- `build_id` path parameter.

**User actions**

- View:
  - Status and cache-hit flag.
  - Profile ID (with link back to `/ui/profiles/{profile_id}`).
  - ImageBuilder info.
  - Timestamps and duration (if available).
- For each artifact:
  - See ID, kind, path, size, checksum.
  - Click "Download" (if a download URL is available).
  - Click "Copy path" (uses JS to copy to clipboard).
  - Click "Flash" → `GET /ui/flash/new?artifact_id={id}`.
- Open the build log file (via `log_path` → URL).

**Backend behavior**

- `builds_service.get_build(db, build_id)`.
- `builds_service.list_artifacts(db, build_id)`.

Rendered template: `builds/detail.html`.

**Role in end-to-end flows**

- Central hub for **artifacts** produced by a build.
- For "write image to TF card":
  1. User confirms the build succeeded and inspects cache_hit/logs if needed.
  2. User chooses the correct artifact (e.g. factory vs sysupgrade image).
  3. User clicks "Flash" on that artifact, which navigates to
     `/ui/flash/new?artifact_id={id}`.

#### 4.3.4. Optional: live status polling – `GET /ui/builds/{build_id}/status-fragment`

**Purpose**

- Allow the GUI to update the status block for a running build without a full
  page reload.

**Inputs**

- `build_id` path parameter.

**User actions**

- None directly; JS can periodically fetch this fragment.

**Backend behavior**

- `builds_service.get_build(db, build_id)` and render a small template fragment
  (e.g. `builds/_status_fragment.html`).

**Frontend behavior**

- In `app.js`, look for an element with `data-poll-url`.
- Periodically `fetch` that URL and replace the element’s `innerHTML`.
- If not implemented, users can simply refresh the entire page.

**Role in end-to-end flows**

- Optional enhancement for long-running builds:
  - Allows users to stay on the build detail page and wait for completion
    before selecting an artifact to flash.

---

### 4.4. Flashing

Flashing must respect all safety constraints in `SAFETY.md` and
`OPERATIONS.md`.

#### 4.4.1. Flash list – `GET /ui/flash`

**Purpose**

- List flash operations and their results.

**Inputs (query parameters)**

- `status` – `succeeded|failed|running|pending` (optional).

**User actions**

- Filter flash history by status.
- Click a flash ID to view detail.

**Backend behavior**

- `flash_service.list_flash_records(db, status=...)`.
- Render `flash/list.html` with:
  - `flashes` – list of flash records.
  - `filters` – current status filter.

Flash record fields generally include:

- `id`
- `artifact_id`
- `build_id` (if tracked)
- `device`
- `status`
- `bytes_written`
- `verification` (mode + result)
- `log_path`
- timestamps

**Role in end-to-end flows**

- Read-only history of past flash operations.
- For "write image to TF card":
  - User may come here **after** a flash to verify outcome or
    cross-check which image was written to which device.

#### 4.4.2. Flash wizard – `GET /ui/flash/new`

**Purpose**

- Provide a safe, explicit way to start flashing.

**Inputs (query parameters)**

- `artifact_id` – optional; pre-select an artifact to flash.

**User actions**

- Confirm artifact (if provided).
- Provide device path manually (`/dev/sdX`).
- Choose options:
  - `verify_mode` (`full`, `prefix-64m`, etc.).
  - `wipe` (boolean).
  - `dry_run` (default: true).
  - `force` (unchecked by default).
- Type the device path again in a confirmation field.

**Backend behavior**

- Optional: `builds_service.get_artifact(db, artifact_id)` if `artifact_id` is
  given.
- Render `flash/wizard.html` with:
  - `artifact` (optional).
  - `form` defaults (`dry_run=True`, etc.).

**Safety requirements**

- Do not auto-detect or suggest block devices.
- Make it clear that flashing can destroy data.
- Require explicit confirmation as described below.

**Role in end-to-end flows**

- This page is reached in two main ways:
  1. From a specific artifact in `/ui/builds/{build_id}` via a "Flash" link
     (ideal path).
  2. Directly (manually entering `artifact_id`) if the user already knows the
     artifact ID.
- For "write image to TF card":
  - User reviews the artifact summary (if provided),
  - Enters the explicit device path,
  - Chooses verification/wipe/dry-run/force,
  - Confirms the device string, then submits to start the flash.

#### 4.4.3. Start flash – `POST /ui/flash`

**Purpose**

- Launch a flash operation using core flash service.

**Inputs (form fields)**

- `artifact_id` – required.
- `device` – required (e.g., `/dev/sdX`).
- `verify_mode` – `full` or `prefix-64m`.
- `wipe` – checkbox.
- `dry_run` – checkbox, default true.
- `force` – checkbox.
- `confirmation` – required, must equal `device`.

**User actions**

- Submit the form.
- If inputs are valid and confirmed, a flash operation is started.
- User is redirected to `GET /ui/flash/{flash_id}`.

**Backend behavior**

1. Confirmation check:

   - Reject the request if `confirmation.strip() != device.strip()`.
   - Re-render the wizard with an error and previous values.

2. Flash call:

   - If confirmation passes, call:

     ```python
     flash_service.flash_artifact(
         db=db,
         artifact_id=artifact_id,
         device=device,
         verify_mode=verify_mode,
         wipe=wipe,
         dry_run=dry_run,
         force=force,
     )
     ```

   - On success: redirect (`303`) to `/ui/flash/{id}`.
   - On failure: re-render `flash/wizard.html` with `error` and form data.

**Safety rules enforced by UX**

- `dry_run` is enabled by default.
- Real writes require all of:
  - `dry_run == False`,
  - `force == True`,
  - `confirmation == device`.

**Role in end-to-end flows**

- Transition point between **user intent** and **actual (or dry-run) device
  operation**.
- For "write image to TF card":
  - On success, the user immediately lands on the flash detail page to review
    status and verification results.

#### 4.4.4. Flash detail – `GET /ui/flash/{flash_id}`

**Purpose**

- Show full information about a flash operation.

**Inputs**

- `flash_id` path parameter.

**User actions**

- View:
  - status (succeeded/failed/running/pending),
  - device path,
  - linked build/artifact,
  - bytes written,
  - verification mode/result,
  - log link (if available).

**Backend behavior**

- `flash_service.get_flash_record(db, flash_id)`.
- Render `flash/detail.html` with a read-only summary.

**Role in end-to-end flows**

- Final stop in the "write image to TF card" journey.
- For "write image to TF card":
  - User verifies that status is `succeeded`,
  - Confirms verification result is `match`,
  - Optionally records/logs `device`, `artifact_id`, and timestamps for
    auditability.

---

## 5. Static assets (functional requirements)

### 5.1. CSS – `web/static/css/style.css`

CSS only needs to ensure:

- Tables and forms are readable.
- Statuses are visually distinguishable via simple colored badges (e.g.
  `.status-succeeded`, `.status-failed`, etc.).
- The layout is plain but not broken; no specific design is required.

No CSS framework is required.

### 5.2. JS – `web/static/js/app.js`

Only minimal vanilla JS is planned:

1. Copy path buttons

   - Behavior:
     - On click of `.btn-copy-path`, read `data-copy` attribute and copy to
       clipboard.

2. Optional: status polling

   - Behavior:
     - On pages that require live updates (build/flash), mark a container with
       `data-poll-url`.
     - JS periodically fetches that URL and replaces the container content.

No external JS libraries are required.

---

## 6. Data dependencies

The GUI depends solely on existing core services and APIs:

- Profiles
  - `profiles_service.list_profiles(...)` – used by `/ui/profiles`.
  - `profiles_service.get_profile(...)` – used by `/ui/profiles/{profile_id}`.
- Builds
  - `builds_service.build_or_reuse(...)` – used by `POST /ui/builds`.
  - `builds_service.list_builds(...)` – used by `/ui/builds` and the
    "recent builds" section of `/ui/profiles/{profile_id}`.
  - `builds_service.get_build(...)` – used by `/ui/builds/{build_id}`.
  - `builds_service.list_artifacts(...)` – used by `/ui/builds/{build_id}`.
  - `builds_service.get_artifact(...)` – used by `/ui/flash/new` when
    `artifact_id` is provided.
- Flash
  - `flash_service.list_flash_records(...)` – used by `/ui/flash`.
  - `flash_service.flash_artifact(...)` – used by `POST /ui/flash`.
  - `flash_service.get_flash_record(...)` – used by `/ui/flash/{flash_id}`.
- Config / health
  - `get_settings()` (and/or health endpoints) for dashboard info.

All `/ui` routes use the same `get_db_session()` and `get_settings()`
dependencies as the JSON routers; the GUI does **not** create its own
database engines or sessions. The GUI must stick to these services and must
not reimplement any underlying build/flash logic.

---

## 7. Error handling

- Existing web APIs map internal exceptions to structured JSON with:
  - `code`: error code (e.g. `validation`, `not_found`, `flash_hash_mismatch`).
  - `message`: human-readable description.
  - `log_path`: path to detailed log, when available.

GUI handlers should:

- Catch service/Web API errors.
- Render templates with:
  - An `error` string visible on the page.
  - A link to `log_path` where appropriate.
- Use HTTP 4xx for user errors (e.g. bad input, failed confirmation).

For flashing and building, errors should be explicit and non-ambiguous.

---

## 8. Phased implementation plan

To implement the design incrementally and safely:

### Phase 1 – Skeleton

- Add `web/routers/gui.py`.
- Register router in `web/app.py` under `/ui`.
- Create `base.html` and `dashboard.html`.
- Implement `GET /ui/` with settings summary.

### Phase 2 – Profiles

- Implement `GET /ui/profiles` and `GET /ui/profiles/{profile_id}`.
- Build templates `profiles/list.html` and `profiles/detail.html`.
- Verify navigation from dashboard → profiles list → profile detail.

### Phase 3 – Builds

- Implement `POST /ui/builds` (build trigger).
- Implement `GET /ui/builds` and `GET /ui/builds/{build_id}`.
- Add artifact list and log link in `builds/detail.html`.

### Phase 4 – Flash

- Implement `GET /ui/flash`, `GET /ui/flash/new`, `POST /ui/flash`,
  `GET /ui/flash/{flash_id}`.
- Enforce safety UX for flashing (dry-run default, force flag, confirmation).
- Test end-to-end using the same fake device pattern used in existing tests.

### Phase 5 – Enhancements (optional)

- Profile create/edit/clone pages.
- Batch build UI around `builds_service.build_batch`.
- Polling fragments and JS.
- GUI-specific tests (`tests/test_web_gui.py`) using `TestClient`.

---

## 9. API contract and stability

The HTML GUI is **secondary** to the JSON/CLI/MCP interfaces, but its
endpoints should still be reasonably stable to avoid disrupting operators.

### 9.1. Route stability

- The following routes are expected to exist across minor/patch releases:
  - `GET /ui/`
  - `GET /ui/profiles`, `GET /ui/profiles/{profile_id}`
  - `POST /ui/builds`, `GET /ui/builds`, `GET /ui/builds/{build_id}`
  - `GET /ui/flash`, `GET /ui/flash/new`, `POST /ui/flash`,
    `GET /ui/flash/{flash_id}`
- Optional routes (status fragments, profile CRUD, batch builds) may be added
  later; if removed or changed, this should be noted in the changelog.

### 9.2. HTML output expectations

HTML structure is intentionally **not** considered a stable API contract, but
tests and operators can rely on the following:

- `GET /ui/profiles`:
  - Returns HTTP 200 on success.
  - Contains at least one link of the form `/ui/profiles/{profile_id}` for
    each profile.
- `GET /ui/builds`:
  - Returns HTTP 200 on success.
  - Contains links of the form `/ui/builds/{build_id}`.
- `GET /ui/flash`:
  - Returns HTTP 200 on success.
  - Contains links of the form `/ui/flash/{flash_id}`.

Error cases:

- When a referenced resource does not exist:
  - `GET /ui/profiles/{profile_id}` → HTTP 404 with a clear message
    (e.g. "Profile not found").
  - `GET /ui/builds/{build_id}` → HTTP 404 with a clear message.
  - `GET /ui/flash/{flash_id}` → HTTP 404 with a clear message.
- When form input is invalid (e.g. bad confirmation, missing device):
  - HTTP 400 with the error message visible on the rendered page.

These conventions should be maintained when evolving the GUI.

---

## 10. Testing strategy

The GUI is tested via FastAPI's `TestClient`, using the same fixtures as the
JSON web API tests. Tests focus on **page availability**, **happy-path flows**,
and **safety behavior**, rather than exact HTML.

### 10.1. Test module

- New test module: `tests/test_web_gui.py`.
- Uses the same app factory / fixtures as `tests/test_web_api.py`.

### 10.2. Core test cases

Planned tests include (names are suggestions):

- `test_ui_dashboard_renders`:

  - `GET /ui/` returns 200.
  - Body contains links to `/ui/profiles`, `/ui/builds`, `/ui/flash`.

- `test_ui_profiles_list_renders`:

  - With at least one profile in the DB, `GET /ui/profiles` returns 200.
  - Body contains that profile's `profile_id` and a link
    `/ui/profiles/{profile_id}`.

- `test_ui_profile_detail_renders`:

  - With a profile and one build for it, `GET /ui/profiles/{profile_id}`
    returns 200.
  - Body includes the profile ID and at least one build link
    `/ui/builds/{build_id}`.

- `test_ui_build_create_redirects`:

  - Given an existing profile, `POST /ui/builds` with `profile_id` and minimal
    form data returns a 303 redirect.
  - `Location` header points to `/ui/builds/{build_id}`.

- `test_ui_builds_list_renders`:

  - With at least one build, `GET /ui/builds` returns 200 and shows the build
    ID and profile ID.

- `test_ui_build_detail_renders`:

  - For an existing build with artifacts, `GET /ui/builds/{build_id}` returns
    200 and includes artifact data and flash links
    (`/ui/flash/new?artifact_id=...`).

- `test_ui_flash_list_renders`:

  - With at least one flash record, `GET /ui/flash` returns 200.
  - Body contains a link `/ui/flash/{flash_id}`.

- `test_ui_flash_wizard_requires_confirmation`:

  - `POST /ui/flash` with `artifact_id`, `device`, but mismatched
    `confirmation` returns 400.
  - Body includes an error message; no new flash record is created.

- `test_ui_flash_dry_run_default`:
  - `POST /ui/flash` with matching confirmation but default `dry_run=True`
    creates a flash record in dry-run mode.
  - Test asserts that the record indicates dry-run (via whatever field the
    service exposes), and no real device writes are attempted in tests.

Where possible, tests should reuse existing fixtures for fake devices and temp
directories used by `flash` tests.

---

## 11. Operational considerations

### 11.1. Deployment and security

- The GUI is intended for local or otherwise **trusted** environments.
- Recommended deployment:
  - Run `uvicorn web:app` (or equivalent ASGI server).
  - Optionally place a reverse proxy with authentication in front of the app
    if exposed over a network.
- Flash endpoints (JSON and GUI) must not be exposed to untrusted users;
  operators are responsible for securing access to `/ui/flash` and the
  underlying `/flash` APIs.

Possible future knob (to be implemented if needed):

- `OWRT_IMG_WEB_ENABLE_FLASH_GUI` (or similar) to **disable** all `/ui/flash`
  routes at startup in environments where GUI flashing is not allowed.

### 11.2. Logging

- GUI handlers should not change existing logging semantics:
  - Build and flash operations are already logged at the service level.
  - The GUI primarily surfaces those operations; additional logging should be
    limited to high-level access/errors where useful.
- For troubleshooting, error pages should surface `log_path` values (when
  available) so operators can quickly locate detailed logs on disk.

---

## 12. Usage

Once implemented:

- Start the web server:

```bash
uv run uvicorn web:app --reload --host 0.0.0.0 --port 8000
```

- Access the GUI:

- `http://localhost:8000/ui/` – dashboard
- `http://localhost:8000/ui/profiles` – profiles
- `http://localhost:8000/ui/builds` – builds
- `http://localhost:8000/ui/flash` – flash history

The GUI remains a minimal, safe, and dependency-light frontend, fully backed by
the existing `openwrt_imagegen` core services and FastAPI web API.

---

## 13. Notes for AI agents (Copilot, etc.)

This section is specifically for AI coding agents that will implement or
maintain the GUI. Humans can ignore or skim it.

### 13.1. High-level rules

- Treat this document as the **source of truth** for GUI behavior.
- Never duplicate business logic that already exists in
  `openwrt_imagegen.*.service` modules.
- GUI routes under `/ui` should:
  - Call core services directly using shared dependencies from `web.deps`.
  - Respect all safety constraints in `SAFETY.md` and `OPERATIONS.md`,
    especially for flashing.
  - Avoid new global state or alternative database engines/sessions.

When in doubt about a behavior, prefer:

1. Reading the relevant service module and tests under `tests/`.
2. Wiring a _thin_ adapter in `web/routers/gui.py` that calls the service.
3. Returning to this design doc and `FRONTENDS.md` for consistency.

### 13.2. Where to put code

- New HTML endpoints: `web/routers/gui.py`.
- Templates: `web/templates/...` as listed in section 2.1.
- Static files: `web/static/css/style.css`, `web/static/js/app.js`.
- Tests: `tests/test_web_gui.py` (reusing fixtures from
  `tests/test_web_api.py`).

Do **not** add GUI-specific logic under `openwrt_imagegen/`; that layer must
remain backend-agnostic and reusable.

### 13.3. How to call services

For each `/ui` route, prefer the following pattern:

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from web.deps import get_db_session, get_settings
from openwrt_imagegen.profiles import service as profiles_service
from openwrt_imagegen.builds import service as builds_service
from openwrt_imagegen.flash import service as flash_service

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/profiles", response_class=HTMLResponse)
def ui_profiles_list(
    request: Request,
    db = Depends(get_db_session),
    q: str | None = None,
):
    profiles = profiles_service.list_profiles(db=db, q=q)
    return templates.TemplateResponse(
        "profiles/list.html",
        {"request": request, "profiles": profiles, "filters": {"q": q}},
    )
```

- Use FastAPI dependency injection (`Depends`) for DB session and settings.
- Do **not** use `requests`/HTTP to call JSON endpoints; call the services
  directly.

Section 6 already maps each `/ui` route to its corresponding service
functions; follow that mapping exactly unless this document is explicitly
updated.

### 13.4. Safety expectations for flashing

When implementing `/ui/flash/new` and `POST /ui/flash`:

- Do not auto-detect devices or guess `/dev/*` paths.
- Enforce the confirmation rule from section 4.4.3:
  - `confirmation.strip() == device.strip()` must hold, otherwise return a
    400 error and re-render the wizard.
- Make `dry_run` the **default** and clearly indicate in the template when a
  real write is requested.
- Only allow real writes when **all** of the following hold:
  - `dry_run is False`;
  - `force is True` (checkbox explicitly checked);
  - confirmation matches the device path.

If in doubt, re-read `docs/SAFETY.md` and mirror the checks that already
exist in the flash service and tests.

### 13.5. Testing requirements

Before considering the GUI implementation complete, make sure at least the
following pass:

1. Lint and type-check:

   ```bash
   uv run ruff check
   uv run mypy openwrt_imagegen
   ```

2. Tests (at minimum):

   ```bash
   uv run pytest tests/test_web_api.py tests/test_web_gui.py tests/test_flash_*.py
   ```

3. Manual smoke test (optional but recommended):

   ```bash
   uv run uvicorn web:app --reload --host 0.0.0.0 --port 8000
   ```

   Then visit `/ui/` and walk through:

   - dashboard → profiles → profile detail,
   - profile detail → build → build detail,
   - build detail → flash wizard → flash detail (dry-run only in dev).

### 13.6. Minimal prompt for Copilot Agent

When running a GitHub Copilot Agent on this repo to implement the GUI, use a
prompt along these lines (adapted as needed):

> You are working in the `openwrt-imagegen-profiles` repo.
> Read and strictly follow `docs/WEB_GUI_FRONTEND_DESIGN.md`,
> `docs/WEB_GUI_PLAN.md`, `docs/FRONTENDS.md`, and `docs/SAFETY.md`.
> Implement the `/ui` web GUI as described there, using FastAPI + Jinja2
> without SPA frameworks.
> Add `web/routers/gui.py`, templates under `web/templates/`, static assets
> under `web/static/`, and tests in `tests/test_web_gui.py`.
> GUI routes must call the existing `openwrt_imagegen` service modules via
> `web.deps` dependencies, not via HTTP to JSON endpoints.
> Prioritize safety for all flashing operations and ensure dry-run-by-default
> behavior.
> Make small, incremental changes, run `ruff`, `mypy`, and `pytest` as
> described in the docs, and keep public JSON/CLI APIs unchanged.

Agents should treat this section as normative unless the repository owners
update it.
