# DB_MODELS.md – database and ORM model concepts

This document describes the intended ORM-backed data model for this project. It
is a design document for how **profiles**, **Image Builders**, **build records**,
**artifacts**, and optional **flash records** should be represented in the
database.

It complements:

- [ARCHITECTURE.md](ARCHITECTURE.md) – overall system responsibilities and data flow.
- [PROFILES.md](PROFILES.md) – profile schema and examples.
- [BUILD_PIPELINE.md](BUILD_PIPELINE.md) – build orchestration and caching.
- [SAFETY.md](SAFETY.md) – TF/SD flashing and safety model.
- [AI_CONTRIBUTING.md](AI_CONTRIBUTING.md) – rules for AI changes, including "DB + ORM as source of truth".

The goal is to keep the DB schema predictable, reproducible, and friendly to
both human operators and AI tools.

---

## 1. Design goals

The data model should:

- Make **profiles, builders, builds, artifacts, and flashes** first-class entities.
- Support reproducibility: given a build record, you can reconstruct what was
  built, with which inputs, and which outputs were produced.
- Enable caching: builds with identical effective inputs can be reused.
- Be ORM-friendly: models map cleanly to tables and relations.
- Stay aligned with the public concepts described in the other docs.

This file is intentionally ORM-agnostic (SQLAlchemy, Django ORM, etc. would
both work), but the shapes and relationships are concrete.

---

## 2. Core entities and relationships

Conceptually, the main entities are:

- **Profile** – immutable build recipe (see [PROFILES.md](PROFILES.md)).
  -- **ImageBuilder** – a cached instance of the official OpenWrt Image Builder
  for a specific `(release, target, subtarget)`.
- **BuildRecord** – one execution of the build pipeline for a particular
  combination of profile + Image Builder + options.
- **Artifact** – a single output file from a build (sysupgrade, factory image,
  manifest, etc.).
- **FlashRecord** (optional/future) – a record of writing an artifact to a
  specific TF/SD card device.

High-level relationships:

- A `Profile` can be used by many `BuildRecord`s.
- An `ImageBuilder` can be used by many `BuildRecord`s.
- A `BuildRecord` has many `Artifact`s.
- A `BuildRecord` can be referenced by many `FlashRecord`s.

---

## 3. Profile model

Profiles are the **source of truth** for how images should be built.
They mirror the schema in `PROFILES.md`.

### 3.1. Fields (suggested)

- `id` (PK, integer or UUID)
- `profile_id` (string, unique, immutable)
- `name` (string)
- `description` (text, nullable)
- `device_id` (string, indexed)
- `tags` (JSON array of strings, or separate tag table)

- `openwrt_release` (string, indexed)
- `target` (string, indexed)
- `subtarget` (string, indexed)
- `imagebuilder_profile` (string)

- `packages` (JSON array of strings)
- `packages_remove` (JSON array of strings)

- `files` (JSON array of objects)

  - Each object contains `source`, `destination`, `mode`, `owner`.

- `overlay_dir` (string, nullable)

- `policies` (JSON object)

  - e.g. `filesystem`, `include_kernel_symbols`, `strip_debug`, `allow_snapshot`, etc.

- `build_defaults` (JSON object)

  - e.g. `rebuild_if_cached`, `initramfs`, `keep_build_dir`, etc.

- `bin_dir` (string, nullable)
- `extra_image_name` (string, nullable)
- `disabled_services` (JSON array of strings)
- `rootfs_partsize` (integer, nullable)
- `add_local_key` (boolean, nullable)

- `created_at` (timestamp)
- `updated_at` (timestamp)
- `created_by` (string, nullable)
- `notes` (text, nullable)

### 3.2. Behavior

- Profiles are treated as **immutable** during builds.
- Schema and semantics must remain compatible with the definitions in
  `PROFILES.md`.
- Changes to a profile are explicit CRUD operations; versioning (e.g. history
  tables) is optional but recommended for reproducibility.

---

## 4. ImageBuilder model

Represents a locally cached instance of an official OpenWrt Image Builder.

### 4.1. Fields (suggested)

- `id` (PK)
- `openwrt_release` (string, indexed)
- `target` (string, indexed)
- `subtarget` (string, indexed)

- `upstream_url` (string)
- `archive_path` (string) – local path to downloaded archive (if kept)
- `root_dir` (string) – path to unpacked builder root

- `checksum` (string, nullable) – e.g. SHA-256 of the archive
- `signature_verified` (boolean, default false)

- `state` (enum/string)

  - e.g. `pending`, `ready`, `broken`, `deprecated`.

- `first_used_at` (timestamp, nullable)
- `last_used_at` (timestamp, nullable)

### 4.2. Behavior

- Keyed by `(openwrt_release, target, subtarget)`.
- Build orchestration (see `BUILD_PIPELINE.md`) ensures the correct ImageBuilder
  exists before a build runs.
- Build records should reference ImageBuilder by foreign key.

---

## 5. BuildRecord model

A `BuildRecord` captures a single build pipeline execution.

### 5.1. Fields (suggested)

- `id` (PK)

- `profile_id` (FK → Profile.id, indexed)
- `imagebuilder_id` (FK → ImageBuilder.id, indexed)

- `status` (enum/string)

  - e.g. `pending`, `running`, `succeeded`, `failed`.

- `requested_at` (timestamp)
- `started_at` (timestamp, nullable)
- `finished_at` (timestamp, nullable)

- `input_snapshot` (JSON or text)

  - Canonical representation of all inputs used for this build:
    - Profile snapshot.
    - Effective package list.
    - Files/overlay info.
    - Image Builder options.
    - Any other build-time options.

- `cache_key` (string, indexed)

  - Hash over `input_snapshot`, as described in `BUILD_PIPELINE.md`.

- `build_dir` (string) – path to working directory (if retained)
- `log_path` (string, nullable) – combined stdout/stderr or log file path

- `error_type` (string, nullable)
- `error_message` (text, nullable)

- `is_cache_hit` (boolean, default false)
  - `true` when this record represents returning an existing build rather than
    executing Image Builder again.

### 5.2. Behavior

- The **cache key** is computed exactly as in `BUILD_PIPELINE.md`:
  - Normalize all relevant inputs → serialize to canonical JSON → hash (e.g. SHA-256).
- Before starting a new build, the system searches for an existing `BuildRecord`
  with the same `cache_key` and `status = succeeded`.
- When a cache hit occurs:
  - Frontends can indicate this to users via `is_cache_hit` or similar fields.

---

## 6. Artifact model

Represents a single file produced by a build (e.g. a sysupgrade or factory
image, a manifest, etc.).

### 6.1. Fields (suggested)

- `id` (PK)
- `build_id` (FK → BuildRecord.id, indexed)

- `kind` (string, nullable)

  - e.g. `sysupgrade`, `factory`, `manifest`, `other`.

- `relative_path` (string)

  - Path relative to a configured artifacts root.

- `absolute_path` (string)

  - Optional; may be derived from `relative_path` and config.

- `filename` (string)
- `size_bytes` (bigint)
- `sha256` (string)

- `labels` (JSON array of strings, nullable)
  - e.g. `for_tf_flash`, `debug_only`.

### 6.2. Behavior

- Artifacts are stored under a predictable directory structure, as described in
  `BUILD_PIPELINE.md` (e.g. `artifacts/<release>/<target>/<subtarget>/<profile_id>/<build_id>/...`).
- `sha256` is computed during the build pipeline and reused by flashing code for
  verification (see `SAFETY.md`).

---

## 7. FlashRecord model (optional / future)

A `FlashRecord` tracks writing a specific artifact to a specific device. It is
not strictly required for basic flashing functionality but is useful for audit
trails and fleet management.

### 7.1. Fields (suggested)

- `id` (PK)

- `artifact_id` (FK → Artifact.id, indexed)
- `build_id` (FK → BuildRecord.id, indexed)

- `device_path` (string)

  - e.g. `/dev/sdX`.

- `device_model` (string, nullable)
- `device_serial` (string, nullable)

- `requested_at` (timestamp)
- `started_at` (timestamp, nullable)
- `finished_at` (timestamp, nullable)

- `status` (enum/string)

  - e.g. `pending`, `running`, `succeeded`, `failed`.

- `wiped_before_flash` (boolean, default false)
- `verification_mode` (string, nullable)

  - e.g. `full-hash`, `prefix-64MiB`.

- `verification_result` (string, nullable)

  - e.g. `match`, `mismatch`, `skipped`.

- `log_path` (string, nullable)

- `error_type` (string, nullable)
- `error_message` (text, nullable)

### 7.2. Behavior

- Flashing logic (see `SAFETY.md`) creates a `FlashRecord` when a flash operation
  is requested, updates status as it proceeds, and records verification results.
- Enables queries like:
  - "Show me all devices flashed with build X".
  - "List all failed flashes for artifact Y".

---

## 8. Indices and querying patterns

To support the workflows described across the docs, the DB should be indexed for
queries like:

- Profiles:

  - By `profile_id`.
  - By `device_id`, `openwrt_release`, `target`, `subtarget`.
  - By tags.

- ImageBuilder:

  - By `(openwrt_release, target, subtarget)`.

- BuildRecord:

  - By `profile_id` (FK).
  - By `imagebuilder_id` (FK).
  - By `status`.
  - By `cache_key`.
  - Latest successful build for a given profile.

- Artifact:

  - By `build_id`.
  - By `kind`.

- FlashRecord (if used):
  - By `artifact_id`, `build_id`.
  - By `device_path`.
  - By `status`.

These patterns should guide index creation regardless of the specific database
engine.

---

## 9. Alignment with other docs

- `PROFILES.md` defines the logical schema for profiles; the `Profile` model here
  is its database representation.
- `ARCHITECTURE.md` states that the database + ORM are the source of truth for
  profiles, Image Builders, builds, and artifacts; this file makes that explicit
  in model form.
- `BUILD_PIPELINE.md` explains how builds are orchestrated and how the cache key
  is computed; `BuildRecord.cache_key` and `BuildRecord.input_snapshot` store that
  information.
- `SAFETY.md` defines flashing safety rules and mentions a potential `FlashRecord`;
  this file sketches that model.
- `AI_CONTRIBUTING.md` instructs AI agents to keep logic in Python modules under
  `openwrt_imagegen/` and to treat DB + ORM as the authoritative state; these
  models are the target for that guidance.

As code is implemented, this document should be kept up to date to reflect the
actual ORM models used by the project.
