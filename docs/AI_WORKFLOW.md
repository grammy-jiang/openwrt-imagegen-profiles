# AI_WORKFLOW.md – AI-only workflows and operations

This document describes how AI agents are expected to work in this repository,
from proposing changes to updating docs and tests. It explains **how to apply** the rules from
[AI_CONTRIBUTING.md](AI_CONTRIBUTING.md) in day-to-day work, and builds on the architecture
defined in [ARCHITECTURE.md](ARCHITECTURE.md).

It is written for AI assistants (and humans supervising them) who are
implementing or modifying functionality in an **AI-first** codebase.

---

## 1. Roles and responsibilities

- **AI agents**:

  - Propose and implement changes to code, docs, and tests.
  - Follow architecture and safety constraints strictly.
  - Keep documentation and implementation in sync.

- **Human maintainers**:
  - Review AI-generated changes.
  - Approve, adjust, or reject changes.
  - Provide additional context or constraints when needed.

The intent is that most implementation work can be performed by AI, while humans
focus on review, policy, and direction.

---

## 2. Before making changes

AI agents should always:

1. **Read the core docs** relevant to the change:

- [README.md](../README.md) – project overview and goals.
- [ARCHITECTURE.md](ARCHITECTURE.md) – system design, responsibilities, and directory layout.
- [PROFILES.md](PROFILES.md) – profile schema and examples.
- [BUILD_PIPELINE.md](BUILD_PIPELINE.md) – how builds and caching work.
- [SAFETY.md](SAFETY.md) – TF/SD flashing safety.
- [DB_MODELS.md](DB_MODELS.md) – ORM model concepts.
- [FRONTENDS.md](FRONTENDS.md) – CLI/web/MCP responsibilities.
- [Copilot instructions](../.github/copilot-instructions.md) – short AI-facing rules.
- [AI_CONTRIBUTING.md](AI_CONTRIBUTING.md) – strict rules and expectations.

2. **Understand the constraints**:

   - Always use the official OpenWrt Image Builder for builds.
   - Database + ORM are the source of truth for profiles, Image Builders,
     builds, artifacts, and (optionally) flash records.
   - Profiles are immutable inputs to builds.
   - Frontends are thin; no business logic duplication.

- Flashing is safety-critical and must follow [SAFETY.md](SAFETY.md).

3. **Identify the right layer** to change:

   - Core library (`openwrt_imagegen/…`).
   - Frontends (`cli`, `web`, `mcp_server`).
   - Docs (`*.md` files).
   - Tests (`tests/`).

---

## 3. Typical AI workflows

### 3.1. Adding a new feature

1. **Clarify the feature**

   - Map the feature to existing concepts: profiles, builds, artifacts, flashing,
     or frontends.

2. **Update design/docs first when necessary**

   - If the feature introduces a new concept (e.g. a new field on Profile or a new
     kind of artifact), update:
     - `ARCHITECTURE.md` (if it changes architecture or responsibilities).
     - `PROFILES.md` (for profile fields).
     - `DB_MODELS.md` (for ORM fields and relationships).
     - `FRONTENDS.md` (if frontend responsibilities change).

3. **Implement core logic**

   - Add or modify functions/classes in `openwrt_imagegen/`:
     - `profiles` for profile-related behavior.
     - `builds` for build pipeline and cache behavior.
     - `imagebuilder` for Image Builder management.
     - `flash` for flashing, honoring `SAFETY.md`.

4. **Wire frontends**

   - Update CLI/web/MCP to call the new or modified core API.
   - Keep these layers thin (no extra business logic).

5. **Add or update tests**

   - Add tests in `tests/` covering:
     - New core functions.
     - New DB model behavior.
     - Error handling and edge cases.

6. **Run tests and adjust**

   - Ensure tests pass locally (or in CI) before changes are proposed.

### 3.2. Adjusting existing behavior

1. **Locate the behavior** in the core library.
2. **Check relevant docs** to see how the behavior is described.
3. **Update implementation and docs together**:
   - If code is more correct than docs, update docs.
   - If docs are authoritative, update code to match.
4. **Confirm downstream impact** on frontends and tests.

### 3.3. Fixing bugs

1. **Reproduce or characterize the bug** using tests or examples.
2. **Add a failing test** that captures the buggy behavior.
3. **Fix the bug** in the smallest reasonable scope in core code.
4. **Update docs** if behavior changes in a user-visible way.
5. **Re-run tests** to confirm the fix.

---

## 4. Documentation discipline

AI agents must treat documentation as a first-class artifact:

- When adding fields or changing semantics:

  - Update `PROFILES.md` for profile changes.
  - Update `DB_MODELS.md` for DB/ORM changes.
  - Update `BUILD_PIPELINE.md` for build orchestration changes.
  - Update `SAFETY.md` for flashing and verification changes.
  - Update `FRONTENDS.md` for CLI/web/MCP behavior changes.

- When ambiguity is found:

  - Prefer to resolve it by clarifying docs **before** implementing behavior.

- When code and docs disagree:
  - Prefer existing, tested code as authoritative.
  - Adjust docs and AI guidance (`AI_CONTRIBUTING.md`, `../.github/copilot-instructions.md`)
    to match, unless the bug is clearly in code and should be fixed.

---

## 5. Testing expectations

AI agents should:

- Favor small, focused tests.
- Avoid tests that require network access, TF/SD hardware, or real Image Builder
  downloads where possible:

  - Use mocks or fakes for Image Builder.
  - Use in-memory or temporary databases.
  - Use fake block devices for flashing tests.

- Ensure tests cover:
  - Happy paths for core workflows (build-or-reuse, flash with verification).
  - Error paths (invalid profiles, missing Image Builder, hash mismatches, etc.).

If adding new CLI or MCP capabilities, include tests that:

- Validate argument/parameter parsing.
- Confirm structured outputs contain required fields.

---

## 6. Review and iteration

A typical AI-driven change cycle should look like:

1. Read relevant docs and existing code.
2. Plan changes (code + tests + docs).
3. Implement core logic.
4. Update docs to reflect new behavior.
5. Add/update tests.
6. Run tests and adjust.
7. Present a concise summary of:
   - What changed.
   - Why it changed.
   - How it was verified.

Human reviewers can then:

- Spot architectural mismatches.
- Tighten constraints or suggest alternative designs.
- Approve or request follow-up changes.

---

## 7. Alignment with core guidelines

This workflow is intentionally aligned with:

- [AI_CONTRIBUTING.md](AI_CONTRIBUTING.md) – golden rules for AI changes.
- [Copilot instructions](../.github/copilot-instructions.md) – compact AI guidance.
- [ARCHITECTURE.md](ARCHITECTURE.md), [PROFILES.md](PROFILES.md), [BUILD_PIPELINE.md](BUILD_PIPELINE.md), [SAFETY.md](SAFETY.md), and
  [DB_MODELS.md](DB_MODELS.md) – authoritative design and data model references.

AI agents should treat these documents as the contract for how to behave in this
repository and keep them up to date as the implementation evolves.
