# Changelog

Notable repo-level changes. The `ticket-review` skill keeps its own
changelog at `skills/skills/ticket-review/CHANGELOG.md` (release history is
git tags).

Format: [Keep a Changelog](https://keepachangelog.com/); versions are
scaffold versions (`scaffold/VERSION`).

## [Unreleased]

- The LLM judge no longer reads a rejection as a pass. `_parse_verdict` did
  `bool(data["pass"])`, and every non-empty string is truthy — so a judge
  replying `{"pass": "false", …}`, an ordinary formatting slip, was recorded
  as **passed**, on the first attempt, with no exception, no retry and
  nothing in `errors` to notice. The safety gate runs at threshold 1.0, so a
  single quoted boolean could turn a failing guardrail assertion into a green
  release gate. Verified directly. Verdicts are now interpreted strictly:
  real booleans, the obvious words (`true`/`yes`/`pass` and
  `false`/`no`/`fail`, case-insensitive), and `0`/`1`; anything ambiguous
  raises, which costs a retry and then fails closed — matching how the rest
  of `judge_assertion` already behaved. Regression tests added, twelve of
  which fail against the previous implementation.
- A crafted `instance.yaml` can no longer forge JSON structure in the
  rendered `settings.json` / `.mcp.json` and escalate its own permissions.
  The templates interpolated instance-supplied strings raw (`"{{ pattern }}"`),
  and validation only requires `extra_allow` / `extra_deny` / `extra_ask` to
  be lists of non-empty strings — so a pattern containing `"], "allow": ["…`
  closed the string and opened a new `allow` key. Python keeps the *last*
  duplicate key, so the injected array silently **replaced** the base
  allow-list. Verified end to end: an instance that `de validate` reports as
  valid built successfully with `allow` reduced to `["Bash(rm -rf /)",
  "Bash(:*)"]` — the entire `Read`/`Grep`/`Glob`/`Skill`/escalate floor gone
  and arbitrary shell granted. The same technique reached `deny`, `env`, the
  `hooks` wiring (skill-gate, injection-detector, escalation-guard) and the
  MCP server map. This defeated precisely the guarantee `merge.py`'s
  monotonicity and shadowing checks exist to provide. Every interpolation in
  the JSON templates now goes through `| tojson`. Output for valid configs is
  byte-identical, so no rebuild is required. Regression tests in
  `scaffold/builder/tests/test_render_injection.py`, six of which fail
  against the previous templates.
- `result-sanitizer` hook no longer crashes (and silently skips credential
  scanning) on structured tool output. PostToolUse `tool_response` is usually
  a dict/list, and the hook ran `re.search` over it directly, raising an
  uncaught `TypeError` — so the credential-leak scan was defeated for exactly
  the outputs most likely to embed secrets (command results, parsed API
  responses). The hook now JSON-serializes non-string output before scanning,
  catching credentials nested inside structured values. Behavioral tests in
  `scaffold/builder/tests/test_result_sanitizer.py`.
- Bridge now warns at startup when no user allowlist is configured
  (`enforce_allowlist_policy`). `auth.is_allowed` fail-opens on an empty
  `allowed_users`, so any signature-valid sender can drive the agent — fine
  as a loopback demo default, but an easy footgun (an open bridge) once the
  bind is off-box. The check logs a plain warning on loopback and an
  escalated one naming the host on a non-loopback bind, mirroring the
  existing signing-secret policy; it warns rather than fails because a real
  signing secret already gates delivery, so an open user list can be a
  deliberate choice. Unit tests in `bridge/tests/test_allowlist_policy.py`.
- Governance console draft path-traversal write fixed: the CONFIG_EDIT
  allowlist's `kb/team/` prefix rule admitted paths like
  `kb/team/../../../etc/x`, which survived the check and only resolved when
  the workspace materializer ran `ws / path`, escaping the temp workspace at
  write time and breaking the "a config change never touches anything
  outside the instance" invariant. `is_allowed` now rejects any absolute
  path or `.`/`..` segment up front (`is_safe_relative_path`), and
  `_materialize_workspace` re-checks each resolved target stays within the
  workspace as defense-in-depth. Traversal/absolute-path cases added to
  `console/tests/test_allowlist.py`.
- Bridge `/mode` no longer lets a non-admin chat user loosen the agent's
  permission mode: the builder's permission-monotonicity rule is now
  enforced on the chat surface too — non-admins may only select a mode
  equal to or stricter than the instance default, and loosening (e.g. to
  `bypassPermissions`) requires admin. Direct unit tests added for
  `auth.py` (allowlist/admin gating) and `commands.py` (dispatch + the
  escalation gate).

### Added
- repo-ci's deterministic eval gates (`de-eval lint`, `de-eval e2e --dry-run`)
  now run over **every** skill in the registry instead of only
  `ticket-review`, discovered by globbing `skills/skills/*/SKILL.md` — so a
  newly added skill is covered the moment it lands, with no workflow edit. A
  skill without CI coverage is a skill nobody is checking; `access-review`
  had none until now. Both skills pass both gates.
- `access-review`, a **second reference skill** — a security/compliance
  worker that reviews a service access-grant request against a least-privilege
  policy (role catalog, production time-boxing, privileged-PII manager
  approval) and posts a comment-only review, never granting or revoking. It
  runs on the same scaffold, security floor, and eval harness as the SRE
  `ticket-review` worker, demonstrating the platform carries a different
  worker archetype unchanged. Deterministic policy logic is gated by
  `eval/tests/test_access_review_logic.py` (13 tests), and the skill passes
  the standing lint + version-check release gates.
- skills-ci `auto-tag` now skips gracefully when `RELEASE_BOT_TOKEN` is not
  configured (mirroring the `ANTHROPIC_API_KEY`-gated jobs) instead of failing
  the push: a repo without the release PAT still validates every deterministic
  gate and can tag releases manually.
- `docs/authoring-a-worker.md`: an author-facing guide for standing up an
  intelligent-staff worker for your own team — from one copied instance
  directory to a validated, doctored, drift-checked runtime. Grounded in the
  exact `de validate/build/doctor/diff` output of a freshly scaffolded worker
  and linked from both READMEs. Complements the demo-focused quickstart by
  documenting the platform's actual adoption path.
- Deterministic CI coverage for the ticket-review skill's core SOP
  decision logic (`analyze.py` R1/R2/R3 + `render_comment.py`): run as
  subprocesses against crafted fixtures in `eval/tests/`, so the digital
  employee's actual PASS/FAIL reasoning is guarded even when the LLM-driven
  gates are skipped (no `ANTHROPIC_API_KEY`).
- `docs/example-review.md`: real, unedited `ticket-review` output for
  the two seeded tickets (PASS + the SOP-violating FAIL), with a one-command
  reproduction — concrete proof of what the digital employee produces,
  linked from both READMEs. No LLM needed; the skill scripts are deterministic.
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
- Session reaping no longer interrupts a turn that is in flight. Both
  reapers — the idle sweeper and LRU eviction at `max_sessions` — chose their
  victim by `last_active_at` and stopped the subprocess without holding the
  session lock, while `send_turn` only refreshed that timestamp *after* the
  turn finished. A turn running longer than `idle_timeout_seconds` therefore
  still carried the previous turn's timestamp and looked like the idlest
  session in the manager, so the sweeper (or, under load, eviction) killed
  the subprocess mid-turn and the user was told "the agent session ended
  unexpectedly — please resend", a failure that never happened. Reproduced
  end to end. `send_turn` now marks activity when the turn starts; both
  reapers skip sessions whose lock is held and take that lock before
  stopping, re-checking liveness and idleness under it. Genuinely idle
  sessions are still reaped. Eviction that finds every live session busy
  logs and starts one more rather than interrupting a conversation. New
  tests in `bridge/tests/test_session_lifecycle.py`, three of which fail
  against the previous implementation.
- A PATH shim can no longer be written outside the shim directory, and the
  strict-replay guarantee is now stated accurately. `first_words` took the
  first token of a `command_prefix` verbatim, so an absolute prefix
  (`/usr/bin/git commit`) yielded the shim name `/usr/bin/git` — and
  `shim_dir / "/usr/bin/git"` discards `shim_dir` entirely in pathlib, so
  `write_shims` would write the shim script over the real binary's path
  (clobbering it where writable, `PermissionError` otherwise). Path
  invocations also bypass `PATH` lookup, so they could never have been
  intercepted: they are now rejected as an authoring error, and
  `write_shims` re-checks containment as defense in depth. The module
  docstring previously claimed "a stray real call can never escape during
  replay"; interception in fact covers exactly the shimmed commands (the
  fixtures' first words plus the deny-set), so the docstring now says that
  precisely. No existing fixture used a path-bearing prefix. New tests in
  `eval/tests/test_shim.py`.
- A failed console draft transition no longer strands the draft or loses the
  error. `validate()` / `build_test()` move the draft into an intermediate
  state (`VALIDATING` / `BUILD_TESTING`) and audit `Started` before shelling
  out to `de`, which runs under a 180s timeout — so `TimeoutExpired` (or any
  workspace-materialisation error) is a routine outcome. Neither was caught:
  the draft stayed in the intermediate state permanently, where no
  transition accepts it as input, and the audit trail stopped at `Started`
  with the error discarded. Reproduced end to end. Both transitions now
  record a `Failed` audit row carrying the exception and return the draft to
  `DRAFT` — the same state a plain non-zero `de` exit lands on — so the
  draft stays recoverable and "every transition writes an audit row" holds.
  The workspace is also materialised inside the `try`, so an error there no
  longer leaks the temp directory. Regression tests cover both transitions,
  a pre-`de` failure, and the untouched happy path.
- Builder no longer accepts an unresolvable skill pin silently. Skills are
  copied from the registry's **working tree**, and the `tag:` pin was only
  used for lock-file metadata: if it named a tag that does not exist (a typo,
  a deleted tag, or a skill that was never released), `git rev-parse` failed,
  `_git_commit` returned `None`, and the build still exited 0 — installing
  something other than the pinned release while `skills-lock.json` recorded
  `"commit": null`. For a project whose headline claim is a versioned
  supply chain of tag-released skills, the pin has to be enforced or at least
  surfaced. `resolve_and_install` now emits a warning naming the unresolvable
  pin. The check is guarded by `_registry_has_tags`, so a shallow/tagless
  checkout (where *nothing* can be verified) does not raise a false alarm on
  every build; `repo-ci`'s builder job now checks out with `fetch-depth: 0`
  so the pin is genuinely validated in CI rather than sitting permanently in
  "cannot verify" mode. Regression tests cover the bad-pin, tagless, and
  unpinned cases.
- skills-ci release pipeline no longer blocks itself. The `lint` and
  `version-check` jobs matrixed over a hardcoded `[ticket-review]`
  **unconditionally**, so any change under `skills/skills/**` (e.g. adding a
  second skill) re-ran `version-check` on the unchanged, already-released
  ticket-review and failed it (`0.1.2` is not strictly greater than the
  existing `ticket-review/v0.1.2` tag) — turning the whole pipeline red on an
  unrelated skill. The gate jobs (lint, version-check, triggers, safety, e2e,
  auto-tag) now derive their matrix from `detect-release`'s changed-skill set
  (`detect_release.py --changed-json` → a `fromJSON` dynamic matrix), so only
  skills that actually changed are gated and auto-tag only tags what changed.
  This unblocks introducing additional skills.
- context-isolator hook (security floor): a prompt containing a ```` ```log ````
  fenced block or an unlabeled fenced code block produced corrupted
  `<untrusted_data>` markup — the loose "log"/"code" context cues (sections
  5/6) re-matched the `data_source="log"`/`"code"` attribute that section 1
  had already inserted and split the tag (`data_source="<untrusted_data …`).
  A corrupted isolation tag can defeat the "treat as external data" guard.
  Those sections now skip any span that already contains inserted tags;
  regression tests added.
- escalation-guard hook (security floor): emitted an invalid ISO-8601
  timestamp (`...+00:00Z`) in every escalation event, and crashed with an
  uncaught `AttributeError` when a tool's output was a structured object
  (dict) instead of a string — silently disabling the circuit breaker for
  those tools. Both fixed; the hook gains subprocess-driven tests.
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
