# Changelog

Notable repo-level changes. The `ticket-review` skill keeps its own
changelog at `skills/skills/ticket-review/CHANGELOG.md` (release history is
git tags).

Format: [Keep a Changelog](https://keepachangelog.com/); versions are
scaffold versions (`scaffold/VERSION`).

## [Unreleased]

### Security
- Bridge `/mode` no longer lets a non-admin chat user loosen the agent's
  permission mode: the builder's permission-monotonicity rule is now
  enforced on the chat surface too — non-admins may only select a mode
  equal to or stricter than the instance default, and loosening (e.g. to
  `bypassPermissions`) requires admin. Direct unit tests added for
  `auth.py` (allowlist/admin gating) and `commands.py` (dispatch + the
  escalation gate).

### Added
- Bridge inbound-text sanitization (`bridge/sanitize.py`): envelope tags,
  spoofed role markers, and control characters are neutralized before
  session injection — governance checklist item 4 moves from
  simplified-for-demo to implemented (demo scope).
- Browser smoke tests for the console SPA (`console/tests_e2e/`,
  playwright) guarding the render contract — including a regression test
  for the startup double-render that once duplicated every fleet card —
  run in CI as `frontend-e2e`.
- CI: `de doctor` + `de diff` drift check on the freshly built instance,
  and `de-eval e2e --dry-run` (fixture runtime build + strict-replay
  wiring, no LLM) on the released skill.
- Containerized demo: `docker compose up --build` boots the mock Change
  Gateway + governance console; the image build and both endpoints are
  smoke-verified by the `docker-demo` CI job on every push.
- Bridge turn timeout (`sessions.turn_timeout_seconds`) and explicit
  recovery replies when the agent subprocess crashes or hangs, with
  resilience tests against the fake-claude harness.
- CI gates: `shellcheck` over the `de` CLI and repo scripts, and the
  deterministic `de-eval lint` gate on the released skill.
- README: draft-workflow and audit-log screenshots, and a "Where this
  fits" positioning section (both languages).
- Root `Makefile`: `make demo` boots the mock Change Gateway + governance
  console in one command; `make test/lint/leak-check/build` mirror CI
  verbatim.
- Tests for the mock Change Gateway (the EXECUTION layer's only write
  path), run in CI as `mocks-tests`.
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
- `de diff` no longer reports a session's hook state as drift: `runtime/work/`
  (gitignored hook state, DESIGN.md S3) is created only after the agent runs
  and was never in the build manifest, so `compute_diff` flagged every
  `work/*` file as `extra` — a false-positive drift on the governance
  centerpiece after any `de start`. That directory is now excluded from the
  scan; `diff.py` gains unit tests (clean/modified/missing/extra + the
  work-state regression).
- Builder: nondeterministic `.build-manifest.json` / `.managed-files.json`
  entry ordering (unsorted skill-file iteration) — consecutive builds are
  now byte-identical.
- Console frontend: initial route rendered twice concurrently, duplicating
  every fleet card.

## [0.1.0] — initial public snapshot

Six-layer intelligent-staff platform demo: scaffold (security floor +
deterministic builder + `de` CLI), one reference instance, versioned skill
registry with release gates, `de-eval` harness (lint / triggers / safety /
e2e strict replay), chat bridge, governance console, and mock Change
Gateway — all inside the fictional Acme Corp universe.
