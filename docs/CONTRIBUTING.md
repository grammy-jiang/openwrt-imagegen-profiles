# Contributing

Thank you for your interest in improving `openwrt-imagegen-profiles`!

This project provides an AI-friendly orchestration layer around the official OpenWrt Image Builder. Before contributing, it helps to read:

- [README.md](../README.md) – overview and goals.
- [ARCHITECTURE.md](ARCHITECTURE.md) – system responsibilities and layout.
- [PROFILES.md](PROFILES.md) – profile schema and examples.
- [BUILD_PIPELINE.md](BUILD_PIPELINE.md) – how builds and caching work.
- [SAFETY.md](SAFETY.md) – TF/SD flashing safety rules.
- [DB_MODELS.md](DB_MODELS.md) – ORM model concepts.
- [FRONTENDS.md](FRONTENDS.md) – CLI, web, MCP frontends.

For AI-specific guidance, also see:

- [AI_CONTRIBUTING.md](AI_CONTRIBUTING.md)
- [AI_WORKFLOW.md](AI_WORKFLOW.md)
- [Copilot instructions](../.github/copilot-instructions.md)

## AI-assisted contributions

If you use AI tools (such as GitHub Copilot agents) while working on this repository,
those tools **must** follow the policies in [AI_CONTRIBUTING.md](AI_CONTRIBUTING.md) and the
runtime instructions in [Copilot instructions](../.github/copilot-instructions.md).

`AI_WORKFLOW.md` describes the expected step-by-step workflow for AI agents (plan, read
docs, make small changes, run tests, update docs, and summarize results).

## Ways to contribute

- Improve or extend design documentation.
- Add or refine profile examples under `profiles/`.
- Implement core Python modules under `openwrt_imagegen/` following the architecture.
- Add tests once the codebase exists.

## Development expectations

- Use Python 3.10+.
- Follow the separation of concerns described in `ARCHITECTURE.md`:
  - Core logic under `openwrt_imagegen/`.
  - Thin frontends for CLI, web, and MCP.
- Treat profiles as immutable inputs and always use the official OpenWrt Image Builder for builds.

Once the Python package and tests are added, please:

- Make sure `pytest` passes before opening a PR.
- Keep docs in sync with any behavioral changes.

## Pull requests

When opening a pull request:

- Describe the problem being solved and the approach you took.
- Link to relevant design docs (architecture, build pipeline, safety rules, etc.).
- Mention any new configuration, environment variables, or migration steps.

Maintainers may ask for small adjustments (naming, structure, extra tests) to keep the project consistent and maintainable.
