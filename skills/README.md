# Skills Repository

This directory contains reusable Claude skills for the DE platform.

## Layout

Skills are organized in `skills/<name>/`, each containing:
- `SKILL.md` — skill definition, metadata, and interface
- `scripts/` — Python scripts implementing the skill pipeline
- `tests/` — test cases, triggers, and mock fixtures
- `pyproject.toml` — Python project configuration
- `uv.lock` — dependency lock file

## Versioning

Skills are released as git tags: `<name>/v<semver>` (e.g., `ticket-review/v0.1.0`).

## CI/Testing

Lint, version checks, triggers validation, safety scanning, and end-to-end testing are configured in a follow-up task.
