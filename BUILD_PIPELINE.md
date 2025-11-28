# Build orchestration and pipeline

This document explains how build orchestration works in this repo:

- How **profiles** become concrete OpenWrt Image Builder invocations.
- How the system selects and manages **Image Builder** instances.
- How **build records** and **artifacts** are created, cached, and reused.
- How different **frontends** (CLI, web, MCP) drive the same core pipeline.

It is a design document only. The authoritative, always-up-to-date reference for the
profile schema lives in [PROFILES.md](PROFILES.md). The overall system architecture is in
[ARCHITECTURE.md](ARCHITECTURE.md). This file zooms in on the build pipeline itself.

## 1. High‑level pipeline

At a high level, building an image for a device profile follows this flow:

1. **Resolve profile**

- Look up the profile definition in the database (or import from YAML/JSON and persist).
- Validate the profile against the schema in [PROFILES.md](PROFILES.md).

2. **Resolve Image Builder**

   - From the profile’s `openwrt_release`, `target`, and `subtarget` fields, find or create the
     corresponding `ImageBuilder` record in the database.
   - If the Image Builder is not present locally, download and unpack it into the
     cache directory, then record metadata (version, checksum, path, status).

3. **Compute build inputs and cache key**

   - Combine:
     - Profile identity (device_id, release, target, subtarget, image_builder_profile).
     - Effective package set (base + profile packages + any extra packages provided at request time).
     - Files/overlays and their content hashes.
     - Image Builder options (BIN_DIR, EXTRA_IMAGE_NAME, ROOTFS_PARTSIZE, DISABLED_SERVICES,
       ADD_LOCAL_KEY, etc.).
     - Global or per-request build flags (e.g. `force_rebuild`, `offline`, `custom_seed`).
   - Normalize these inputs into a deterministic **build cache key** (e.g. a structured
     JSON blob that is then hashed).

4. **Check for existing build (cache lookup)**

   - Query the database for a `BuildRecord` whose cache key exactly matches the computed key
     and whose status is a successful completion state.
   - If found, return the existing build’s artifacts instead of rebuilding
     (unless the caller explicitly requested `force_rebuild`).

5. **Prepare build working directory**

   - Create a fresh working directory under the Image Builder cache tree, e.g.:
     - `cache/<release>/<target>/<subtarget>/builds/<device_id>/<build_id>/`
   - Materialize overlays and files into the `FILES` tree for this build.
   - Optionally inject additional metadata (e.g. `manifest.json`) into the build directory.

6. **Compose Image Builder command**

   - Build a single `make` invocation equivalent to what a human would run:

     ```sh
     make image \
       PROFILE="<profile_name>" \
       PACKAGES="<full_pkg_list>" \
       FILES="<files_dir>" \
       BIN_DIR="<bin_dir>" \
       EXTRA_IMAGE_NAME="<extra_name>" \
       DISABLED_SERVICES="<disabled_services>" \
       ROOTFS_PARTSIZE="<rootfs_partsize>" \
       ADD_LOCAL_KEY="<add_local_key>"
     ```

- All of these values are derived from the resolved profile + any per-request overrides.
- The exact mapping from profile fields to these variables is documented in [PROFILES.md](PROFILES.md).

7. **Execute build**

   - Spawn the Image Builder process in the appropriate directory with the composed
     arguments, capturing:
     - Stdout/stderr (for logs).
     - Exit code.
   - Enforce configurable timeouts and resource limits where appropriate.

8. **Collect outputs and compute checksums**

   - Discover generated images (e.g. `*-sysupgrade.bin`, `*-factory.bin`, etc.) from the
     configured `BIN_DIR`.
   - Compute content hashes (e.g. SHA-256) for all artifacts.
   - Record file sizes and other metadata.

9. **Persist BuildRecord and artifacts**

   - Create/update a `BuildRecord` in the database:
     - Link to the profile and the Image Builder used.
     - Store the normalized input description and the cache key.
     - Store the build status, timestamps, and log locations.
   - Create associated `Artifact` records for each generated image, with paths
     and checksums.

10. **Return build result**
    - Frontends receive a structured summary of the build:
      - Build ID and status.
      - Profile and Image Builder references.
      - Artifacts (type, filename, path, checksum, size).
      - Log references.

This pipeline is designed to be deterministic, idempotent, and cache-aware: the same
inputs should always produce either a cache hit or an identical new build.

## 2. Inputs and cache key design

### 2.1. What goes into a build input

To make caching correct and predictable, **all materially relevant inputs** to a build
must be captured in the cache key. At a minimum this includes:

- **Profile identity**

  - `device_id`
  - `openwrt.release`
  - `openwrt.target` and `openwrt.subtarget`
  - `openwrt.image_builder_profile`

- **Package set**

  - Base packages implied by the Image Builder profile.
  - Packages explicitly listed in the profile.
  - Any extra packages added at request time.

- **Overlays / FILES directory**

  - The set of overlay directories / files.
  - A robust content hash for the fully materialized `FILES` tree.

- **Image Builder options**

  - `BIN_DIR`, `EXTRA_IMAGE_NAME`, `ROOTFS_PARTSIZE`, `DISABLED_SERVICES`, `ADD_LOCAL_KEY`,
    and any other options that affect the produced images.

- **Environment / global flags**
  - Flags like `force_rebuild` are _not_ part of the cache key (they override cache
    behavior rather than define the build), but other environment knobs that change
    build outputs (e.g. a `RANDOM_SEED` if used) must be included.

### 2.2. Normalization and hashing

The core library should:

- Represent the full set of build inputs as a structured object (e.g. a Python dict
  or a small dataclass) with well-defined keys.
- Serialize this object to a canonical form (e.g. JSON with sorted keys and normalized
  values).
- Compute a strong hash (e.g. SHA-256) over the canonical representation.
- Store both the canonical representation and the hash on the `BuildRecord`.

This makes it easy to:

- Detect cache hits by matching on the hash.
- Inspect build inputs later by reading the canonical representation.
- Evolve the schema in the future while remaining explicit about which version of the
  cache key format was used.

## 3. Image Builder management

The pipeline treats the official OpenWrt Image Builder as an **external, versioned tool**.
The Python core is responsible for:

- Discovering which Image Builder archive is required for a profile
  (based on release/target/subtarget).
- Downloading it from the official sources when needed.
- Verifying its integrity (checksums, optionally signatures).
- Unpacking it into a cache location.
- Recording a durable `ImageBuilder` record in the database with:
  - Release, target, subtarget.
  - Download URL or source.
  - Local path.
  - Checksums and verification status.
  - State (e.g. `ready`, `broken`, `deprecated`).

Frontends never download Image Builders themselves. They only request builds from the
core APIs; the core ensures the appropriate Image Builder is present and ready.

## 4. Build records and artifact tracking

### 4.1. BuildRecord lifecycle

A `BuildRecord` conceptually goes through these states:

1. **pending** – created when the build request is accepted and inputs are normalized.
2. **running** – once the Image Builder process has been spawned.
3. **succeeded** – Image Builder exited successfully and artifacts were collected.
4. **failed** – Image Builder failed (non-zero exit code, timeout, or other error).

Intermediate and final states are persisted so that:

- Long-running builds can be observed and resumed/inspected.
- Failed builds have durable logs and inputs for debugging.
- Successful builds can be reused as cache hits.

### 4.2. Artifact metadata

Each build may produce one or more images. For each artifact, the system records at least:

- Build that produced it.
- Artifact type (e.g. `sysupgrade`, `factory`), if detectable.
- Relative or absolute filesystem path.
- Filename.
- Size (bytes).
- Hash (e.g. SHA-256).
- Optional labels (e.g. `for_tf_flash`, `debug_only`).

Artifacts are stored on disk under a predictable structure that mirrors the logical
relationships:

- By default: `artifacts/<release>/<target>/<subtarget>/<profile_id>/<build_id>/...`

## 5. Frontend flows (CLI, web, MCP)

All frontends follow the same core pipeline, differing only in how they:

- Authenticate/authorize the user (web, MCP).
- Collect and validate inputs (arguments, JSON bodies, etc.).
- Present the result (human-readable vs JSON).

### 5.1. CLI flow

Typical CLI flow for building an image:

1. Parse arguments to select a profile (by device_id or DB id) and any overrides
   (extra packages, overlays, image name suffix, etc.).
2. Call the core `build_image` API with a structured request object.
3. Display:
   - Whether the result was a cache hit or a new build.
   - Build ID and status.
   - Paths and checksums of produced images.
   - Hints for next steps (e.g. flashing via a separate command).

### 5.2. Web flow

Typical web/API flow:

1. Authenticate the user.
2. Accept a JSON build request (profile reference + overrides).
3. Call the same core `build_image` API.
4. Return a JSON response with the build summary, suitable for polling or streaming
   updates.

### 5.3. MCP server flow

Typical MCP tool behavior:

1. Accept a structured tool invocation (e.g. "build image for profile X with extra
   packages Y").
2. Call the same core `build_image` API.
3. Return a machine-friendly summary compatible with MCP conventions
   (stable IDs, URLs or paths for artifacts, logs, etc.).

In all cases, frontends **never** reimplement cache key logic, Image Builder
invocation details, or artifact scanning.

## 6. Error handling and observability

The pipeline should provide:

- Clear, structured error types for common failure modes:
  - Profile not found or invalid.
  - Image Builder missing or invalid.
  - Build process failed (with captured logs).
  - Filesystem or permission issues.
- Rich logging around:
  - Image Builder downloads and verification.
  - Build start/stop and exit codes.
  - Cache hits vs misses.

This information feeds both human debugging (CLI/web logs) and AI tooling
(e.g. MCP-based agents that can inspect past builds and suggest fixes).

## 7. Relationship to flashing

Flashing TF/SD cards is **intentionally separated** from the build pipeline:

- Build orchestration is responsible for producing and tracking images.
- Flashing orchestration is responsible for safely writing those images to
  block devices.

The only shared surface is that flashing commands refer to artifacts produced
by the build pipeline (typically by build ID + artifact ID or by filesystem path).
Flashing rules and safety guarantees are documented separately in `SAFETY.md`.
