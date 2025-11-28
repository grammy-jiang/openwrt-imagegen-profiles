# SAFETY.md – TF/SD card flashing and operational safety

This document consolidates the safety rules, verification steps, and operator guidance
for TF/SD card flashing in this project. It complements the high-level design in
`ARCHITECTURE.md`, the AI rules in `AI_CONTRIBUTING.md`, and the build-focused details in
`BUILD_PIPELINE.md`.

Flashing is treated as a **separate, safety-critical workflow** layered on top of the
build pipeline. The build pipeline produces and tracks images; the flashing layer writes
those images to explicit block devices with strong verification.

---

## 1. Scope and mental model

The system splits responsibilities as follows:

- **Build pipeline** (see `BUILD_PIPELINE.md`):

  - Produces images from profiles using the official OpenWrt Image Builder.
  - Tracks artifacts, checksums, and build metadata in the database.

- **Flashing pipeline** (this document):
  - Accepts a specific image (or build/artifact reference).
  - Writes that image to an explicit TF/SD card device.
  - Verifies that the data on the device matches the source image.
  - Logs operations and surfaces failures clearly.

This separation ensures that changing flashing behavior does not affect image
reproducibility, and that risky operations (block device writes) remain isolated
and auditable.

---

## 2. Non-negotiable safety rules

Any implementation of TF/SD card flashing in this repository **must** respect these rules.
They apply to both human-written and AI-generated code.

1. **Whole-device only**

   - Only operate on whole-device paths like `/dev/sdX`, `/dev/mmcblk0`, etc.
   - Never operate directly on partitions such as `/dev/sdX1` or `/dev/mmcblk0p1`.

2. **No guessing of devices**

   - The caller must provide an explicit device path.
   - The flashing module must not auto-select a device based on size, label, mount
     points, or other heuristics.
   - If a UI (CLI or web) offers shortcuts like "recently used devices", they must
     still lead to an explicit, user-confirmed path.

3. **Explicit confirmation / force flags**

   - Destructive operations require explicit confirmation or a `--force`/equivalent flag,
     especially in interactive tools.
   - Non-interactive contexts (CI, MCP) must use explicit flags or configuration to
     enable flashing; default behavior should be "no flashing".

4. **Pre-flight validation**

   Before writing, the flashing module should:

   - Check that the path exists and is a block device.
   - Refuse to operate on obviously dangerous devices (e.g. system root device) if
     such checks are practical for the environment.
   - Optionally check that the device is not mounted, or at least warn loudly.

5. **Optional wipe / signature clearing**

   - Support an optional pre-write "wipe" step, controlled by a flag or profile policy:
     - Clear known filesystem/partition signatures (similar to `wipefs`).
     - Optionally zero-fill the beginning of the device.
   - Make these operations explicit and well-logged; never perform them implicitly
     without user or caller intent.

6. **Synchronous, flushed writes**

   - Writes must be fully flushed before reporting success, equivalent to using
     `conv=fsync` with `dd` and then calling `sync`.
   - As a rule: when the API reports success, the card should be safe to remove
     (subject to OS/device quirks).

7. **Hash-based verification**

   - After writing, read back from the device and compute a hash
     (e.g. SHA-256) over:
     - Either the full image, or
     - A sufficiently large, well-documented prefix (e.g. first 16–64 MiB), when
       full verification is too slow.
   - Compare the device hash to the source image hash.
   - Treat mismatches as hard failures and surface them clearly.

8. **Ghost-write and bad-media detection**

   - Some TF/SD cards exhibit "ghost write" behavior: writes appear to succeed,
     but the data read back is old or inconsistent.
   - Hash verification is the first line of defense; beyond that, the module
     should:
     - Log discrepancies clearly.
     - Optionally mark devices as "suspect" in logs/metadata so operators can
       retire them.

9. **Detailed logging**

   - Log at least:
     - Device path.
     - Image path and checksum.
     - Bytes written.
     - Whether a wipe was performed.
     - Verification method and result.
   - Logs must be linkable to build IDs and artifact IDs where possible.

10. **No silent failures**

    - All errors (I/O, permission, verification failures, etc.) must produce clear
      error messages.
    - APIs should return structured error types/codes so frontends and AI tools
      can distinguish between failure modes (e.g. "device not block", "hash mismatch",
      "permission denied").

---

## 3. Flashing workflow

A typical flashing run follows these steps:

1. **Select image**

   - Operator or caller specifies an image via:
     - Direct filesystem path, **or**
     - Build ID + artifact ID (recommended), which the system resolves to a path
       and checksum via the database.

2. **Select device**

   - Operator or caller provides an explicit block device path (e.g. `/dev/sdX`).
   - The system may show a list of detected devices with size and model, but the
     final choice is explicit and confirmed.

3. **Pre-flight checks and (optional) wipe**

   - Validate the device path.
   - Confirm (or enforce via flag) that the device is unmounted.
   - If requested, perform signature clearing / partial zero-fill.

4. **Write image**

   - Stream the image to the device, tracking bytes written.
   - Flush device and OS caches before proceeding.

5. **Verify**

   - Read back from device and compute a verification hash.
   - Compare to the image hash.

6. **Record result**

   - Emit logs with all relevant metadata.
   - Optionally store a "flash record" in the database, referencing:
     - Build/artifact used.
     - Device path (and possibly model/serial, if available).
     - Result and any warnings.

7. **Post-flash guidance**

   - Frontends should guide the operator on:
     - Safely removing the card.
     - Booting the device.
     - Verifying the running system (see next section).

---

## 4. Post-boot validation and build IDs

The system should make it easy to verify that a device is running the expected build.
This is coordinated between the build and flashing layers.

1. **Embed a build ID or marker**

   - During image build, the system can:
     - Inject a small file into the filesystem (e.g. `/etc/openwrt-imagegen-build-id`).
     - Embed a marker in `/etc/banner` or similar.
     - Use UCI config or another standard location for metadata.
   - The embedded marker should at minimum contain a stable build ID and profile ID.

2. **Operator verification**

   - After boot, the operator can:
     - SSH into the device.
     - Read the marker file or banner.
     - Confirm that the build ID and profile match what was flashed.

3. **AI / automation guidance**

   - CLI/web/MCP tools should:
     - Include instructions (or links) in their output explaining how to verify.
     - Expose the expected build ID/profile ID in machine-readable output so
       higher-level automation can reason about it.

This mechanism is not part of the flashing process itself, but flashing should
produce enough metadata (e.g. build ID and artifact reference) that frontends
can surface correct verification instructions.

---

## 5. Operator-facing guidance

For human operators using CLI or web UI, the following practices are recommended.

1. **Identify the correct device**

   - Use tools like `lsblk`, `fdisk -l`, or OS-specific disk utilities to identify
     the TF/SD card.
   - Double-check size and model before passing the device path to the tool.

2. **Ensure the device is not mounted**

   - Unmount all partitions from the card before flashing.
   - On Linux, you can use `lsblk` and `umount` to manage this.

3. **Prefer artifact references over raw paths**

   - When possible, refer to images by build ID and artifact ID rather than typing
     raw filesystem paths. This reduces mistakes and ensures the correct image
     is used.

4. **Always review dry-run output**

   - Use a dry-run mode to see exactly what the tool plans to do:
     - Device path, image path, bytes to be written.
     - Whether a wipe will be performed.
   - Only proceed if the dry-run output looks correct.

5. **Handle errors carefully**

   - If hash verification fails, **do not** trust the card:
     - Re-run the operation only after inspecting logs.
     - Consider replacing the card.

6. **Track card provenance when needed**

   - For lab or fleet environments, consider labeling cards and noting which
     build was last flashed, especially for devices used in testing.

---

## 6. Integration points with the rest of the system

### 6.1. With the build pipeline

- Flashing routines accept images by build/artifact reference or file path.
- They rely on build metadata (checksums, file sizes) recorded by the build
  pipeline to:
  - Validate source image integrity before writing.
  - Produce consistent logs tying flashes back to specific builds.

### 6.2. With the database

- Optional future work (documented here for alignment):

  - A `FlashRecord` ORM model linking:
    - BuildRecord / Artifact.
    - Device path (and optionally model/serial info).
    - Time of flashing.
    - Result and verification status.
  - This would allow queries like:
    - "Which images were flashed to this device path?"
    - "Show all devices that were flashed with build X.".

### 6.3. With frontends (CLI, web, MCP)

- Frontends should:
  - Expose dry-run and force flags clearly.
  - Present verification results in both human-readable and machine-friendly
    forms.
  - Avoid hiding or downplaying failures; a failed verification must be
    prominently visible.

---

## 7. AI-specific notes

AI agents working on flashing-related code must also follow:

- `AI_CONTRIBUTING.md` – for overall safety rules and expectations.
- `.github/copilot-instructions.md` – for a condensed version of those rules.

In particular:

- Do not introduce shortcuts that auto-select devices.
- Do not weaken or remove hash verification.
- Keep all flashing logic inside clear, testable Python functions under
  `openwrt_imagegen/flash/`.
- Ensure there are tests (with mocked devices, not real hardware) for:
  - Pre-flight validation.
  - Hash verification logic.
  - Error propagation and logging.

If documentation and code ever disagree, treat the current code as
authoritative but update this document and the AI-facing docs to match.
