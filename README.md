# openwrt-imagegen-profiles

Curated OpenWrt Image Builder profiles and Python tooling for reproducible, automated firmware builds across multiple devices.

This repository is for people who have **multiple OpenWrt devices** and want a single, automated way to:

- Define how each device’s image should be built.
- Build those images reproducibly using the official OpenWrt Image Builder.
- Safely write images to TF/SD cards.
- Reuse existing images instead of rebuilding when nothing has changed.

At a high level, the project provides:

- A **Python orchestration core** that dynamically downloads and caches the official OpenWrt Image Builder.
- A **database-backed profile and build system** for managing per-device recipes and build history.
- An **image cache** that avoids unnecessary rebuilds.
- Multiple frontends over the same logic:
  - A **CLI** for developers and CI.
  - A **web interface** for interactive use.
  - An **MCP server** so AI tools can request builds and flashes programmatically.

The focus is on opinionated, repeatable workflows for a specific set of devices—not on replacing the full OpenWrt SDK.

For a detailed architecture overview (data model, Image Builder management, artifact tracking, TF card safety), see `ARCHITECTURE.md`.
