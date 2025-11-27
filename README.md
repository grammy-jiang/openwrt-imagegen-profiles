# openwrt-imagegen-profiles

Opinionated tooling for managing **OpenWrt Image Builder** runs and TF/SD card flashing across many devices, with profiles and builds tracked in a database.

Use this project if you have **multiple OpenWrt devices** and you want to:

- Describe how each device should be built (target, packages, files) as a reusable profile.
- Build images reproducibly via the official OpenWrt Image Builder, not custom firmware logic.
- Reuse cached images when inputs have not changed instead of rebuilding every time.
- Safely write images to TF/SD cards with verification to catch ghost writes and bad media.

Under the hood, everything is driven by a shared Python library that:

- Dynamically downloads and caches the official OpenWrt Image Builder (keyed by release/target/subtarget).
- Stores profiles, Image Builder metadata, build records, and artifact paths in a database via an ORM.
- Maintains an image cache with build-or-reuse semantics keyed by profile + Image Builder + options.
- Orchestrates safe TF/SD card flashing, including optional wipes and hash-based verification.

Frontends are thin adapters over that library:

- A **CLI** for local use and CI.
- A **web interface** for interactive control.
- An **MCP server** so AI tools can request builds, list artifacts, and trigger flashes programmatically.

This project does **not** replace the OpenWrt SDK or Image Builder; it wraps the official tools with higher-level workflows, safety checks, and persistent metadata.

- For the detailed architecture (data model, Image Builder management, artifact tracking, TF card safety), see `ARCHITECTURE.md`.
- For the profile schema and concrete profile examples, see `PROFILES.md`.
- For AI/agent-specific contribution rules and expectations, see `AI_CONTRIBUTING.md` and `.github/copilot-instructions.md`.
