# Web GUI Plan

This document describes a minimal, dependency-light web GUI for `openwrt-imagegen-profiles`. The GUI is built on top of the existing FastAPI web API in `web/`, uses server-rendered HTML via Jinja2 templates, and relies on small amounts of vanilla JavaScript and CSS.

The goals are:

- Keep the stack and structure simple.
- Reuse the existing FastAPI backend and JSON APIs.
- Avoid heavy frontend frameworks or build tooling.
- Provide a practical, safe UI for profiles, builds, artifacts, and flashing.

---

## 1. High-level design

- **Backend**: existing FastAPI app in `web/app.py`.
- **Rendering**: server-side HTML via Jinja2 templates.
- **Client-side behavior**: minimal vanilla JavaScript (optional small helpers for polling and form UX), basic CSS.
- **API usage**: HTML routes call into the same services/endpoints as the JSON API; no business logic in the GUI.
- **Security / scope**: intended for local or trusted environments; flashing operations must remain explicit and conservative.

The GUI lives alongside the existing web API, mounted under `/ui`.

---

## 2. Routing and structure

### 2.1. Backend structure

- Add a new router module, for example:
  - `web/routers/gui.py` – FastAPI `APIRouter` for HTML pages.
- Register it in `web/app.py`:
  - `app.include_router(gui_router, prefix="/ui", tags=["gui"])`.

Directory layout additions:

- `web/templates/`

  - `base.html` – shared layout, navigation, flash messages.
  - `dashboard.html` – `/ui/` home.
  - `profiles_list.html` – `/ui/profiles`.
  - `profile_detail.html` – `/ui/profiles/{id}`.
  - `builds_list.html` – `/ui/builds`.
  - `build_detail.html` – `/ui/builds/{id}`.
  - `flash_list.html` – `/ui/flash`.
  - `flash_wizard.html` – `/ui/flash/new` (wizard to start a flash).

- `web/static/`
  - `css/style.css` – basic layout and styling.
  - `js/app.js` – minimal JavaScript helpers (optional).

### 2.2. Top-level pages

All GUI routes are read-only HTML over the JSON API or thin POST handlers that proxy to the existing services.

- `GET /ui/` – dashboard / home
- `GET /ui/profiles` – profiles list
- `GET /ui/profiles/{profile_id}` – profile detail
- `GET /ui/builds` – builds list
- `GET /ui/builds/{build_id}` – build detail
- `POST /ui/builds` – trigger a build, then redirect to build detail
- `GET /ui/flash` – flash records list
- `GET /ui/flash/new` – flash wizard (with `artifact_id` query param)
- `POST /ui/flash` – start a flash, then redirect to flash status
- `GET /ui/flash/{flash_id}` – flash status detail

Batch builds and profile CRUD can be added under `/ui/builds/batch` and `/ui/profiles/new`/`/ui/profiles/{id}/edit` as later phases.

---

## 3. Pages and flows

### 3.1. Dashboard (`GET /ui/`)

Purpose:

- Provide an entry point for humans.
- Show links to the main sections and a quick health/config snapshot.

Backend behavior:

- Fetch high-level info (or reuse existing dependencies):
  - Health status from the `GET /health` endpoint or directly via internal logic.
  - Effective config from `GET /config` or `web.deps.get_settings()`.
- Render `dashboard.html` with:
  - Links to Profiles, Builds, Flash.
  - Read-only config fields such as cache directory, artifacts directory, DB path/URL (masked), offline mode.

### 3.2. Profiles

#### 3.2.1. List (`GET /ui/profiles`)

- Calls web API `GET /profiles` with optional query parameters:
  - `release`, `target`, `subtarget`, tag filters, and text search as supported.
- Renders a table:
  - Columns: profile ID, device name/label, release, target/subtarget, tags.
  - Toolbar/filter row for basic filtering.
- Each row links to `GET /ui/profiles/{profile_id}`.

#### 3.2.2. Detail (`GET /ui/profiles/{profile_id}`)

- Calls web API `GET /profiles/{id}`.
- Displays profile information in a key–value layout:
  - OpenWrt release, target, subtarget.
  - Image Builder profile name.
  - Package sets (base, extra, removed).
  - Overlay configuration summary.
  - Tags and metadata.
- Actions:
  - “Build this profile” button that posts to `POST /ui/builds` with this `profile_id`.
  - “Clone” button (later phase) that opens a pre-filled create form.

#### 3.2.3. Optional CRUD (later phase)

- `GET /ui/profiles/new` – render a form using the same schema fields described in `profiles/schema.py`.
- `POST /ui/profiles` – call backend `POST /profiles` and redirect on success.
- `GET /ui/profiles/{id}/edit` – pre-fill form from `GET /profiles/{id}`.
- `POST /ui/profiles/{id}` – call backend `PUT /profiles/{id}` and redirect.

All validation logic remains in the backend; the GUI surfaces error messages from structured responses.

### 3.3. Builds

#### 3.3.1. List (`GET /ui/builds`)

- Calls `GET /builds` with optional filters:
  - `profile_id`, `status` (succeeded, failed, running, pending), date range.
- Renders a table:
  - Columns: build ID, profile ID, status, cache_hit flag, created_at.
  - Status shown with simple colored badges.
- Each row links to `GET /ui/builds/{build_id}`.

#### 3.3.2. Create / trigger (`POST /ui/builds`)

- HTML form (e.g. on profile detail page) posts to `/ui/builds` with:
  - Required: `profile_id`.
  - Optional: `force_rebuild`, extra packages, remove packages, extra image name, etc., mapped to the build service API.
- Backend handler:
  - Validates POSTed fields.
  - Calls the existing build API/service (e.g. `POST /builds` or internal call to `build_or_reuse`).
  - On success, redirects to `/ui/builds/{build_id}` for the new or reused build.
  - On error, re-renders the form with an error message.

#### 3.3.3. Detail (`GET /ui/builds/{build_id}`)

- Calls:
  - `GET /builds/{id}` for metadata.
  - `GET /builds/{id}/artifacts` for artifacts.
- Displays:
  - Status and cache_hit.
  - Profile ID and link back to `/ui/profiles/{profile_id}`.
  - Image Builder info (release, target, subtarget).
  - Timestamps and duration if available.
- Artifacts table:
  - Columns: artifact ID, kind (factory, sysupgrade, rootfs, checksums, etc.), size, checksum.
  - Actions:
    - “Download” (direct link or via a small proxy endpoint).
    - “Copy path” (implemented via a small JavaScript helper).
    - “Flash” (link to `/ui/flash/new?artifact_id=...`).
- Logs:
  - Link to the log file from `log_path`, or
  - Embedded read-only log viewer (simple `<pre>` with scroll).

#### 3.3.4. Status updates

To keep dependencies minimal:

- Option A (simplest): the user manually refreshes the page.
- Option B (small JS):
  - Add a tiny polling script in `app.js` that periodically issues a `fetch` to:
    - Either `GET /ui/builds/{id}/fragment` (HTML partial), or
    - `GET /builds/{id}` (JSON) and updates status text.
  - This requires only vanilla `fetch` and DOM updates, no additional libraries.

### 3.4. Flashing

Flashing is safety-critical and must follow the rules in `SAFETY.md` and `OPERATIONS.md`.

#### 3.4.1. List (`GET /ui/flash`)

- Calls `GET /flash` from the web API.
- Shows a table of flash records:
  - Columns: flash ID, artifact ID, device path, status, verification result, timestamp.
  - Each row links to `GET /ui/flash/{flash_id}`.

#### 3.4.2. Wizard (`GET /ui/flash/new`)

- Accepts an optional query param `artifact_id` (typically set from a “Flash” button on an artifact row).
- Renders a multi-section form:
  - **Artifact**:
    - Shows artifact information (ID, kind, size, checksum) if `artifact_id` is provided.
  - **Device**:
    - Text input for device path (e.g. `/dev/sdX`).
    - The UI must not guess or auto-select devices.
  - **Options**:
    - Checkbox `dry_run` (default checked).
    - Checkbox `wipe`.
    - Checkbox `force` – must be checked for actual write operations.
    - Verification mode select: `full` vs `prefix-64m` (with the same default as the backend).
  - **Confirmation**:
    - A confirmation input where the user must type the device path exactly to enable submission.

#### 3.4.3. Start flash (`POST /ui/flash`)

- Handler accepts form fields, then calls backend `POST /flash` with:
  - `artifact_id` or explicit `image_path`.
  - `device`.
  - `verify_mode`, `wipe`, `dry_run`, `force`.
- On success, redirect to `/ui/flash/{flash_id}`.
- On error, re-render the form with an error message and preserve entered values.

#### 3.4.4. Flash status (`GET /ui/flash/{flash_id}`)

- Calls `GET /flash` filtered by ID or a dedicated `GET /flash/{id}` if available.
- Shows:
  - Status (succeeded, failed, running, pending).
  - Device path.
  - Artifact ID and link to its build.
  - Bytes written.
  - Verification mode and result.
  - Log path and a link to open the log.
- Optional small JS polling to refresh status periodically; or instruct the user to reload.

Safety UX rules:

- Do not display or guess available block devices.
- `dry_run` should be the default.
- Actual writes require:
  - `dry_run` disabled, and
  - `force` enabled, and
  - confirmation input matching the device path.

---

## 4. Dependencies and simplicity

The GUI intentionally uses a small, conservative stack:

- **FastAPI** – already in use for JSON APIs (`web/app.py`).
- **Jinja2** – already referenced in `docs/DEVELOPMENT.md` for server-rendered pages.
- **Vanilla JavaScript** – in a single `web/static/js/app.js` file, used only where needed (polling build/flash status, copy-to-clipboard, basic form enhancements).
- **CSS** – in a single `web/static/css/style.css`, with simple layout and styling.

No additional frontend frameworks (React/Vue/Svelte), no bundlers (webpack/Vite), and no complex asset pipeline are required.

Optionally, if desired but not required, a small third-party file can be served from `web/static/`:

- `htmx` – to simplify partial page updates using HTML attributes, still without a full SPA.

The default plan works fully without htmx or any extra JS libraries.

---

## 5. Data flow and integration

### 5.1. Alignment with existing APIs

The GUI must not introduce new business logic. Instead, it:

- Calls existing services under `openwrt_imagegen/` via the FastAPI web layer.
- Uses the same JSON response shapes and error codes already validated by tests in `tests/test_web_api.py`.
- Maps errors to user-visible messages while preserving structured codes for logs.

The underlying operations are:

- Profiles:
  - `GET /profiles`, `GET /profiles/{id}`, `POST /profiles`, `PUT /profiles/{id}`, `DELETE /profiles/{id}`.
- Builders:
  - `GET /builders`, `GET /builders/{release}/{target}/{subtarget}`, `POST /builders/ensure`, `POST /builders/prune`, `GET /builders/info`.
- Builds:
  - `GET /builds`, `GET /builds/{id}`, `GET /builds/{id}/artifacts`, `POST /builds/batch`, and the single-build endpoint for build-or-reuse.
- Flash:
  - `GET /flash`, `POST /flash`.

The GUI routes must call these endpoints or the equivalent internal service functions, so CLI, web API, and MCP server all stay consistent.

### 5.2. Error handling

- Backend exceptions are already mapped to structured JSON with `code`, `message`, `log_path` per `OPERATIONS.md`.
- GUI handlers should:
  - Inspect the response status and JSON where appropriate.
  - Extract human-readable `message` and display it in a banner or inline form error area.
  - Optionally show a link to `log_path` for deeper diagnosis.

---

## 6. Phased implementation plan

To keep changes manageable and easy to test, implement the GUI in phases.

### Phase 1 – Skeleton and dashboard

- Add `web/routers/gui.py` and register it in `web/app.py` under `/ui`.
- Add `base.html` with navigation and a placeholder content block.
- Implement `GET /ui/` dashboard:
  - Show links to Profiles, Builds, Flash.
  - Display minimal health/config summary.
- Add `style.css` and wire it into `base.html`.

Outcome: you can visit `http://localhost:8000/ui/` and see a basic dashboard.

### Phase 2 – Profiles (read-only)

- Implement `GET /ui/profiles` and `GET /ui/profiles/{profile_id}` using the existing profiles API.
- Build `profiles_list.html` and `profile_detail.html`.
- Add basic filters on the list page.

Outcome: profiles are navigable entirely from the GUI.

### Phase 3 – Builds

- Implement `POST /ui/builds` and add a “Build this profile” button on profile detail.
- Implement `GET /ui/builds` and `GET /ui/builds/{build_id}` with a simple artifacts table and log links.
- Optionally add a small polling script on the build detail page to refresh status.

Outcome: builds can be triggered and inspected from the GUI.

### Phase 4 – Flashing

- Implement `GET /ui/flash` and `GET /ui/flash/{flash_id}`.
- Implement `GET /ui/flash/new` and `POST /ui/flash` with the safety-focused wizard UX.
- Enforce `dry_run` as the default, explicit `force`, and typed device confirmation.
- Optionally add polling to the flash status page.

Outcome: controlled, explicit flashing workflows are available via GUI.

### Phase 5 – Enhancements (optional)

- Add profile CRUD (create/edit/clone) based on backend support.
- Add batch build UI around `POST /builds/batch`.
- Improve styling, add small quality-of-life JavaScript helpers.
- Extend tests in `tests/test_web_api.py` or a new `tests/test_web_gui.py` to:
  - Instantiate the FastAPI app and hit `/ui` routes using `TestClient`.
  - Assert that HTML renders successfully and includes key elements.

---

## 7. Usage

Once implemented, the development and usage workflow for the GUI remains simple:

- Start the server from the project root:

```bash
uv run uvicorn web:app --reload --host 0.0.0.0 --port 8000
```

- Open the GUI in a browser:

- `http://localhost:8000/ui/` – dashboard
- `http://localhost:8000/ui/profiles` – profiles
- `http://localhost:8000/ui/builds` – builds
- `http://localhost:8000/ui/flash` – flash history

All core behavior continues to be driven by the `openwrt_imagegen` library, with the GUI acting as a minimal, human-friendly layer over the existing web API.

---

## 8. Notes for AI agents

This plan is intended to be implemented both by humans and by AI coding
agents (e.g., GitHub Copilot Agent). For agents working in this repo:

- Treat `docs/WEB_GUI_FRONTEND_DESIGN.md` as the **detailed spec** for
  routes, templates, data flow, and safety rules.
- Do not introduce new business logic into `web/` or `docs/`; instead, call
  existing services in `openwrt_imagegen.*.service` modules via `web.deps`
  dependencies.
- Prefer small, incremental changes:
  - Implement Phase 1–4 in order (section 6 of this document).
  - After each phase, run linting and targeted tests.

A minimal task prompt for agents could be:

> Read `docs/WEB_GUI_PLAN.md`, `docs/WEB_GUI_FRONTEND_DESIGN.md`,
> `docs/FRONTENDS.md`, and `docs/SAFETY.md`.
> Implement the `/ui` FastAPI + Jinja2 GUI as described there, without SPA
> frameworks.
> Add `web/routers/gui.py`, templates under `web/templates/`, static files
> under `web/static/`, and tests in `tests/test_web_gui.py`.
> Use `web.deps` to obtain DB sessions and settings, and call the
> `openwrt_imagegen` service modules directly rather than HTTP-calling the
> JSON endpoints.
> Respect all flashing safety requirements (dry-run by default, force flag,
> explicit device confirmation).
> Keep JSON/CLI/MCP public APIs unchanged and ensure `ruff`, `mypy`, and
> `pytest` all pass.

For more detailed agent guidance, see section 13 of
`docs/WEB_GUI_FRONTEND_DESIGN.md`.
