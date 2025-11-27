# PROFILES.md – Profile schema & examples

This document defines the **profile schema** for `openwrt-imagegen-profiles` and gives concrete examples.

Profiles are the **declarative recipes** that describe how to build OpenWrt images for specific devices. They are:

- Stored primarily in the **database via ORM**.
- Optionally imported/exported as **YAML/JSON/TOML** files for editing, review, and version control.
- Treated as **immutable inputs** to builds (never mutated during a build).

The same logical schema applies both to DB models and to on-disk profile files.

---

## 1. Conceptual model

At a high level, a **profile** answers:

- "For this device, with this OpenWrt release and Image Builder, what should the image contain and how should it be built?"

Core concepts:

- **Profile** – top-level recipe, uniquely identified by a stable `profile_id`.
- **Image Builder variant** – `(release, target, subtarget, imagebuilder_profile)` combination the profile expects.
- **Packages** – extra packages to include and (optionally) packages to remove.
- **Files/overlays** – additional files to inject into the image (e.g. SSH keys, configs, banners).
- **Policies** – portable knobs for build behavior (e.g. strip debug, include kernel symbols, filesystem preference).
- **Metadata** – human-friendly tags, comments, and internal bookkeeping.

Image Builder itself exposes a small set of variables (for example `PROFILE`, `PACKAGES`, `FILES`, `BIN_DIR`, `EXTRA_IMAGE_NAME`, `DISABLED_SERVICES`, `ROOTFS_PARTSIZE`, `ADD_LOCAL_KEY`) that control how images are built. Profiles do not expose these low-level variables directly; instead, they use higher-level fields which the Python build library translates into the appropriate Image Builder variables.

---

## 2. Top-level profile fields

The logical schema (DB and file formats) uses these fields.

### 2.1 Identity & device targeting

- `profile_id` (string, required, immutable)

  - Globally unique stable identifier; used in the database and CLIs.
  - Recommended format: `owner.device.release` or `site-room-device`, e.g.:
    - `lab.router1.openwrt-23.05`
    - `home.ap-livingroom.22.03`

- `name` (string, required)

  - Human-readable short name, e.g. `"Living room AP (AX1800, 23.05)"`.

- `description` (string, optional)

  - Longer free-form description: deployment context, constraints, notes.

- `device_id` (string, required)

  - Your canonical label for the physical device, e.g. `"home-ap-livingroom"` or a serial number.
  - Not necessarily unique across releases; `profile_id` is the unique key.

- `tags` (list of strings, optional)

  - Useful for grouping/filtering: `["lab", "wifi", "ax1800", "23.05"]`.

### 2.2 OpenWrt / Image Builder selection

These fields describe **which Image Builder** this profile is intended for and which internal Image Builder profile to use.

- `openwrt_release` (string, required)

  - Example: `"23.05.2"` or `"22.03.5"`.
  - Must match a release managed in the Image Builder metadata table.

- `target` (string, required)

  - OpenWrt target, e.g. `"ath79"` or `"ramips"`.

- `subtarget` (string, required)

  - OpenWrt subtarget, e.g. `"generic"` or `"mt7621"`.

- `imagebuilder_profile` (string, required)

  - The `PROFILE=` value used with Image Builder (e.g. `"tplink_archer-c6-v3"`).
  - Must correspond to a profile known to the selected Image Builder variant.

### 2.3 Packages

Profiles control both **additional packages** and optionally packages to **remove** from defaults.

- `packages` (list of strings, optional)

  - Extra packages to install on top of the Image Builder's default set.
  - Example: `["luci", "luci-ssl", "htop"]`.

- `packages_remove` (list of strings, optional)

  - Packages to explicitly remove from the default profile package set.
  - Example: `["ppp", "ppp-mod-pppoe"]`.

Notes:

- Exact package names must be valid for the selected Image Builder.
- The build library is responsible for turning these lists into the `PACKAGES` argument for Image Builder. Includes from `packages` are passed as-is; excludes from `packages_remove` are prefixed with `-` (for example `-ppp -ppp-mod-pppoe`) to match Image Builder semantics.
- Dependencies do not need to be listed explicitly; the Image Builder uses `opkg` to resolve them. As in the upstream documentation, ABI-versioned packages (for example names like `libubus20191227`) should generally be omitted from profiles and allowed to be pulled in via dependencies instead.

### 2.4 Files and overlays

Profiles can specify additional **files** to be overlaid into the image filesystem.

- `files` (list of file spec objects, optional)

  Each entry:

  - `source` (string, required)

    - Path on the **host** (relative to some `profiles/` or repository root, or absolute); how this is resolved is part of the build configuration.
    - Should usually be a path inside the repo (e.g. `"profiles/files/home-ap-livingroom/etc/banner"`).

  - `destination` (string, required)

    - Path **inside the image filesystem**, e.g. `"/etc/banner"`.

  - `mode` (string, optional)

    - File mode (octal string), e.g. `"0644"` or `"0600"`. Optional if default is acceptable.

  - `owner` (string, optional)

    - User and optionally group; e.g. `"root:root"`.

  Example file spec:

  ```yaml
  files:
    - source: profiles/files/home-ap-livingroom/etc/banner
      destination: /etc/banner
      mode: "0644"
      owner: root:root
  ```

- `overlay_dir` (string, optional)

  - A directory of additional files to be overlayed at build time.
  - Example: `"profiles/overlays/home-ap-livingroom"`.

Implementation detail:

- On disk, `files` and `overlay_dir` can be used in combination; the build library is responsible for constructing a single overlay directory tree and passing it via the `FILES` variable to Image Builder. This directory is typically placed in the Image Builder root or a temporary location and referenced as `FILES="<resolved-path>"` when running `make image`.

### 2.5 Policies and build options

These are **profile-level defaults** for how images should be built. They should map onto Image Builder flags and/or internal behavior.

- `policies` (object, optional)

  Common fields (intentionally generic; the build library must interpret them):

  - `filesystem` (string, optional)

    - Preferred root filesystem type, e.g. `"squashfs"`, `"ext4"`.
    - The orchestrator may choose the closest available image variant.

  - `include_kernel_symbols` (bool, optional)

    - Whether to prefer images with kernel debug symbols (if available).

  - `strip_debug` (bool, optional)

    - Whether to favor images/packages with debug data stripped.

  - `auto_resize_rootfs` (bool, optional)

    - Hint that post-flash scripts/tools should resize rootfs to fill the device (if supported).

  - `allow_snapshot` (bool, optional, default `false`)

    - Whether this profile may target snapshot/unreleased builds.

Profiles may add more policy fields over time, but they must remain **interpretable** by the orchestration library.

### 2.6 Build-time defaults

These influence **build requests** that do not explicitly override them.

- `build_defaults` (object, optional)

  Example fields:

  - `rebuild_if_cached` (bool, optional; default `false`)

    - If `true`, builds for this profile default to "force rebuild" instead of "build-or-reuse".

  - `initramfs` (bool, optional)

    - Whether to also build initramfs images by default (if supported by Image Builder).

  - `keep_build_dir` (bool, optional)

    - Hint for whether to keep intermediate build directories.

Frontends may expose these as CLI flags or web options with sensible overrides.

### 2.8 Image Builder options

These fields describe defaults for how the orchestrator calls the underlying OpenWrt Image Builder. They are translated into the official Image Builder variables described in the upstream documentation.

- `bin_dir` (string, optional)

  - Maps to the Image Builder `BIN_DIR` make variable.
  - If set, the orchestrator will pass `BIN_DIR="<path>"` to `make image` (and related commands) so images are written to that directory instead of the default `bin/targets/...` tree inside the Image Builder.

- `extra_image_name` (string, optional)

  - Maps to `EXTRA_IMAGE_NAME`.
  - This string is appended (after Image Builder sanitizes it) to output image filenames, making it easy to distinguish variants such as `lab-debug` vs `prod`.

- `disabled_services` (list of strings, optional)

  - Maps to `DISABLED_SERVICES`.
  - Each entry is the name of a service in `/etc/init.d/` that should be disabled in the generated image (for example `dnsmasq`, `firewall`, `odhcpd`).

- `rootfs_partsize` (integer, optional)

  - Maps to `ROOTFS_PARTSIZE` (specified in megabytes).
  - Overrides the default rootfs partition size if the target supports it.

- `add_local_key` (bool, optional)

  - Maps to `ADD_LOCAL_KEY`.
  - When `true`, the orchestrator will pass `ADD_LOCAL_KEY=1` so a locally generated signing key is stored in built images, mirroring the upstream `make help` behavior.

### 2.7 Profile provenance / metadata

- `created_by` (string, optional)

  - Origin: e.g. `"human:alice"`, `"ai:github-copilot"`, etc.

- `created_at` (timestamp, optional)

  - DB-managed; omitted in on-disk files or treated as metadata.

- `updated_at` (timestamp, optional)

  - DB-managed; same as above.

- `notes` (string, optional)

  - Free-form comments for maintainers.

---

## 3. On-disk schema (YAML)

YAML is the primary human-editable export/import format. A profile YAML file corresponds to one logical profile.

### 3.1 Minimal example (simple AP)

The file `profiles/home-ap-livingroom.yaml` in this repository is a concrete instance of this minimal profile:

```yaml
profile_id: home.ap-livingroom.23.05
name: Home AP (Living Room, 23.05)
description: >
  Main Wi-Fi access point in the living room.
  OpenWrt 23.05, minimal extras.

device_id: home-ap-livingroom
tags:
  - home
  - ap
  - wifi
  - 23.05

openwrt_release: "23.05.2"
target: ath79
subtarget: generic
imagebuilder_profile: tplink_archer-c6-v3

packages:
  - luci
  - luci-ssl
  - htop

packages_remove:
  - ppp
  - ppp-mod-pppoe

files:
  - source: profiles/files/home-ap-livingroom/etc/banner
    destination: /etc/banner
    mode: "0644"
    owner: root:root

policies:
  filesystem: squashfs
  include_kernel_symbols: false
  strip_debug: true

build_defaults:
  rebuild_if_cached: false
  initramfs: false
```

### 3.2 Example with overlay and snapshot policy

The file `profiles/lab-router1-snapshot.yaml` demonstrates overlays and snapshot usage:

```yaml
profile_id: lab.router1.snapshot
name: Lab Router 1 (Snapshot)
description: |
  Lab router for testing snapshot builds and experimental packages.
  Prefer ext4, keep debug symbols.

device_id: lab-router1
tags:
  - lab
  - router
  - snapshot
  - debug

openwrt_release: "snapshot"
target: ramips
subtarget: mt7621
imagebuilder_profile: xiaomi_mi-router-4a-gigabit

packages:
  - luci
  - tcpdump
  - iperf3
  - kmod-usb-storage
  - block-mount

packages_remove: []

overlay_dir: profiles/overlays/lab-router1

policies:
  filesystem: ext4
  include_kernel_symbols: true
  strip_debug: false
  allow_snapshot: true

build_defaults:
  rebuild_if_cached: true
  initramfs: true
  keep_build_dir: true

notes: >
  Used for performance and regression testing.
  Expect frequent rebuilds and upgrades.
```

### 3.3 Multi-AP fleet with shared pattern

The file `profiles/home-ap-bedroom.yaml` shows another AP in the same fleet:

```yaml
profile_id: home.ap-bedroom.23.05
name: Home AP (Bedroom, 23.05)

device_id: home-ap-bedroom
tags: [home, ap, wifi, 23.05, bedroom]

openwrt_release: "23.05.2"
target: ath79
subtarget: generic
imagebuilder_profile: tplink_archer-c6-v3

packages:
  - luci
  - luci-ssl
  - wpad-basic-mbedtls
  - collectd

files:
  - source: profiles/files/home-ap-bedroom/etc/banner
    destination: /etc/banner

policies:
  filesystem: squashfs

build_defaults:
  rebuild_if_cached: false
```

---

### 3.4 Example with extended Image Builder options

The file `profiles/lab-router1-extended.yaml` demonstrates use of additional Image Builder options:

```yaml
profile_id: lab.router1.extended
name: Lab Router 1 (Extended Image Options)
description: >
  Example profile demonstrating Image Builder options like BIN_DIR,
  EXTRA_IMAGE_NAME, DISABLED_SERVICES, and ROOTFS_PARTSIZE.

device_id: lab-router1
tags: [lab, router, debug, extended]

openwrt_release: "23.05.2"
target: ramips
subtarget: mt7621
imagebuilder_profile: xiaomi_mi-router-4a-gigabit

packages:
  - luci
  - nano
  - openvpn-openssl
packages_remove:
  - ppp
  - ppp-mod-pppoe

overlay_dir: profiles/overlays/lab-router1

policies:
  filesystem: ext4
  include_kernel_symbols: true
  strip_debug: false

build_defaults:
  rebuild_if_cached: true
  initramfs: false

# Fields corresponding to Image Builder variables
bin_dir: /var/tmp/openwrt-images/lab
extra_image_name: lab-debug
disabled_services:
  - dnsmasq
  - firewall
  - odhcpd
rootfs_partsize: 256
add_local_key: true
```

---

## 4. JSON representation

For tools that prefer JSON, the schema is identical, just represented as JSON. Example:

```json
{
  "profile_id": "home.ap-livingroom.23.05",
  "name": "Home AP (Living Room, 23.05)",
  "device_id": "home-ap-livingroom",
  "tags": ["home", "ap", "wifi", "23.05"],
  "openwrt_release": "23.05.2",
  "target": "ath79",
  "subtarget": "generic",
  "imagebuilder_profile": "tplink_archer-c6-v3",
  "packages": ["luci", "luci-ssl", "htop"],
  "packages_remove": ["ppp", "ppp-mod-pppoe"],
  "files": [
    {
      "source": "profiles/files/home-ap-livingroom/etc/banner",
      "destination": "/etc/banner",
      "mode": "0644",
      "owner": "root:root"
    }
  ],
  "policies": {
    "filesystem": "squashfs",
    "include_kernel_symbols": false,
    "strip_debug": true
  },
  "build_defaults": {
    "rebuild_if_cached": false,
    "initramfs": false
  }
}
```

---

## 5. Import/export behavior and DB mapping

### 5.1 Importing a profile file

When importing from YAML/JSON:

1. Validate required fields:
   - `profile_id`, `name`, `device_id`, `openwrt_release`, `target`, `subtarget`, `imagebuilder_profile`.
2. Normalize optional fields:
   - Treat missing lists as empty lists.
   - Treat missing objects as empty objects.
3. Look up or create corresponding DB entities:
   - Associate with an existing Image Builder variant `(release, target, subtarget)` or record that it must be fetched.
4. Insert or update the **profile record**:
   - The system may treat some changes as creation of a **new version** vs in-place update, depending on policy (to be defined in the builds/profiles modules).

### 5.2 Exporting a profile from the DB

When exporting:

1. Select a profile by `profile_id` (and possibly version).
2. Serialize to YAML/JSON with the same field names as above.
3. Optionally include DB-managed timestamps and provenance in a `meta` section, e.g.:

   ```yaml
   meta:
     created_at: "2025-11-28T12:34:56Z"
     updated_at: "2025-11-28T13:00:00Z"
     created_by: ai:github-copilot
   ```

The core schema (`profile_id`, `openwrt_release`, `target`, etc.) should remain stable over time to keep imports/exports predictable.

---

## 6. Profile validation rules

Key rules the validation layer should enforce:

- **Identity**
  - `profile_id` must be non-empty, match a safe pattern (e.g. `^[a-zA-Z0-9_.-]+$`), and be unique.
  - `name` non-empty, within a sane length.
- **OpenWrt / Image Builder**
  - `openwrt_release`, `target`, `subtarget`, `imagebuilder_profile` must not be empty.
  - Optionally validate that this combination exists in Image Builder metadata.
- **Packages**
  - `packages`/`packages_remove` elements are non-empty strings without whitespace.
- **Files**
  - `destination` must start with `/`.
  - `mode` if present must be a valid octal string.
- **Policies**
  - `filesystem`, if set, must be one of a supported set (e.g. `squashfs`, `ext4`).
  - If `openwrt_release` is `"snapshot"` but `allow_snapshot` is not `true`, treat as invalid or warn.
- **Size/complexity**
  - Reasonable limits on list sizes and strings to avoid accidental huge profiles.

---

## 7. How profiles interact with builds

When calling the build library (e.g. `build_or_reuse(profile_id, options)`):

- The **effective build inputs** are:

  - Profile fields (`profile_id` -> DB lookup).
  - Resolved Image Builder variant (from `openwrt_release`, `target`, `subtarget`).
  - Any additional build-time options from CLI/web/MCP.

- The build library:

  - Constructs the Image Builder command using `target`, `subtarget`, `imagebuilder_profile`, `packages`, `packages_remove`, and any `policies`.
  - Ensures the Image Builder archive is present (using the imagebuilder module).
  - Computes a cache key from `profile snapshot + Image Builder + options`.
  - Either reuses an existing artifact or performs a new build.

Conceptually, for a given profile the build library maps profile fields to the official Image Builder variables as follows:

- `imagebuilder_profile` → `PROFILE="<profile-name>"` (as listed by `make info`).
- `packages` + `packages_remove` → `PACKAGES="pkg1 pkg2 -pkg3 …"`.
- `files` + `overlay_dir` → `FILES="<resolved overlay dir>"`.
- `bin_dir` → `BIN_DIR="<path>"` (optional).
- `extra_image_name` → `EXTRA_IMAGE_NAME="<string>"` (optional).
- `disabled_services` → `DISABLED_SERVICES="svc1 svc2 …"` (optional).
- `rootfs_partsize` → `ROOTFS_PARTSIZE="<size-in-MB>"` (optional).
- `add_local_key` → `ADD_LOCAL_KEY=1` when enabled.

For example, a build for the `lab.router1.extended` profile above might translate into a call similar to:

```sh
make image \
  PROFILE="xiaomi_mi-router-4a-gigabit" \
  PACKAGES="luci nano openvpn-openssl -ppp -ppp-mod-pppoe" \
  FILES="<resolved overlay dir>" \
  BIN_DIR="/var/tmp/openwrt-images/lab" \
  EXTRA_IMAGE_NAME="lab-debug" \
  DISABLED_SERVICES="dnsmasq firewall odhcpd" \
  ROOTFS_PARTSIZE="256" \
  ADD_LOCAL_KEY=1
```

Profiles themselves are **not** mutated by builds; build results live in separate build records referencing the profile.

---
