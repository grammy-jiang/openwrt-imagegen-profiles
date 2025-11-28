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
- A **web interface** for interactive control (planned).
- An **MCP server** so AI tools can request builds, list artifacts, and trigger flashes programmatically (planned).

This project does **not** replace the OpenWrt SDK or Image Builder; it wraps the official tools with higher-level workflows, safety checks, and persistent metadata.

## Quick start

```bash
# Create and activate a virtual environment
uv venv .venv
source .venv/bin/activate

# Install with development dependencies
uv pip install -e .[dev]

# Verify the CLI works
python -m openwrt_imagegen --help
python -m openwrt_imagegen --version
python -m openwrt_imagegen config --json
```

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the full development guide.

```bash
# Run linting and type checks
uv run ruff check
uv run ruff format --check
uv run mypy openwrt_imagegen

# Run tests with coverage
uv run pytest --cov --cov-report=term-missing
```

## Documentation

- For the detailed architecture (data model, Image Builder management, artifact tracking, TF card safety), see [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- For the profile schema and concrete profile examples, see [PROFILES.md](docs/PROFILES.md).
- For build orchestration and cache behavior, see [BUILD_PIPELINE.md](docs/BUILD_PIPELINE.md).
- For TF/SD flashing safety rules and operator guidance, see [SAFETY.md](docs/SAFETY.md).
- For database/ORM model concepts, see [DB_MODELS.md](docs/DB_MODELS.md).
- For frontend responsibilities (CLI, web, MCP), see [FRONTENDS.md](docs/FRONTENDS.md).
- For AI/agent-specific contribution rules and expectations, see [AI_CONTRIBUTING.md](docs/AI_CONTRIBUTING.md), [AI_WORKFLOW.md](docs/AI_WORKFLOW.md), and [Copilot instructions](.github/copilot-instructions.md).

## AI usage

If you use AI tools (for example GitHub Copilot agents) with this repository, those
tools must follow the policies in [AI_CONTRIBUTING.md](docs/AI_CONTRIBUTING.md) and the
runtime instructions in [Copilot instructions](.github/copilot-instructions.md).

[AI_WORKFLOW.md](docs/AI_WORKFLOW.md) describes the expected step-by-step workflow for AI
agents (plan, read docs, make small changes, run tests, update docs, and summarize
results).
