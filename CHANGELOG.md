# Changelog

Notable repo-level changes. The `ticket-review` skill keeps its own
changelog at `skills/skills/ticket-review/CHANGELOG.md` (release history is
git tags).

Format: [Keep a Changelog](https://keepachangelog.com/); versions are
scaffold versions (`scaffold/VERSION`).

## [Unreleased]

### Added
- Repo-root CI (`repo-ci`): ruff lint floor, fictional-universe leak check,
  builder merge-invariant tests, validate+build of the reference instance
  with a build-determinism double-build check, and the bridge / console /
  eval pytest suites.
- Unit tests for the two previously untested components: builder merge
  invariants + skill-gate hook behavior (`scaffold/builder/tests/`), and the
  eval harness's deterministic core — frontmatter, judge verdict parsing and
  retry policy, strict-replay fixture matching, PATH-shim generation
  (`eval/tests/`).
- Bilingual README (`README.md` / `README.zh-CN.md`) with architecture
  diagram, badges, and governance-console screenshots; MIT `LICENSE`;
  `CONTRIBUTING.md`; `SECURITY.md`; issue and PR templates.

### Changed
- `skills-ci.yml` moved from `skills/.github/` (where GitHub never executes
  workflows) to the repo root; its eval-harness gates now resolve correctly
  and run live when an `ANTHROPIC_API_KEY` secret is configured.
- skill-gate hook hardened: malformed hook input fails closed, and a Skill
  invocation now opens a time-boxed tool window
  (`DE_SKILL_GATE_TTL_SECONDS`, default 900s) instead of a permanent
  session-wide grant (DESIGN.md D8).
- Bridge refuses to bind beyond loopback with the default demo signing
  secret.

### Fixed
- Builder: nondeterministic `.build-manifest.json` / `.managed-files.json`
  entry ordering (unsorted skill-file iteration) — consecutive builds are
  now byte-identical.
- Console frontend: initial route rendered twice concurrently, duplicating
  every fleet card.

## [0.1.0] — initial public snapshot

Six-layer Digital Employee platform demo: scaffold (security floor +
deterministic builder + `de` CLI), one reference instance, versioned skill
registry with release gates, `de-eval` harness (lint / triggers / safety /
e2e strict replay), chat bridge, governance console, and mock Change
Gateway — all inside the fictional Acme Corp universe.
