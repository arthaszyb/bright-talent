# de-eval

Evaluation harness implementing `docs/40-evaluation/eval-spec.md` against the
artifacts that already exist in this repo: the scaffold builder
(`scaffold/builder/`), the `de` CLI, `skills/skills/ticket-review/tests/`,
and `mocks/change_gateway.py`. `de-eval` never re-implements the build — it
shells out to the real builder to materialize a fixture runtime.

## Install / run

```bash
# from de-demo/
uv run --project eval de-eval <subcommand> [target] [flags]
```

`de-eval` is a console-script (`uv run --project eval de-eval ...`); `uv`
resolves its own venv under `eval/.venv/` on first run.

## Subcommands

| Subcommand | What it checks | Agent execution | Pass rule |
|---|---|---|---|
| `lint [skill-dir]` | SKILL.md frontmatter, no bare `Bash`, required test files, coverage-table consistency | none | single pass/fail |
| `triggers [skill-dir]` | `tests/triggers.yaml` routing (`should_trigger`/`should_not_trigger`) | yes | ratio >= `pass_threshold` (yaml, default 0.9) |
| `safety [skill-dir]` | `tests/safety.yaml` guardrail cases, judged | yes | ratio >= `pass_threshold` (yaml, default 1.0) |
| `e2e [skill-dir]` | `tests/*.mock.yaml` command-replay + judge | yes (unless `--dry-run`) | all cases must pass (both execution and semantic axes) |

`target` defaults to `cwd` if it contains `SKILL.md`, else to
`skills/skills/ticket-review` relative to `cwd` (the demo's one skill) —
pass an explicit path for anything else.

Common flags:
- `--cases <glob>` — filter which case ids / mock-file names run.
- `--report <path>` — write a JSON verdict report to this path.
- `triggers` / `safety` / `e2e` also accept `--rebuild-fixture` (force a
  fresh fixture-runtime build, bypassing the cache).
- `e2e` also accepts `--dry-run` — builds/loads the fixture runtime,
  generates the shim dir, starts and stops the fixture server per case, and
  prints the shim names + fixture-prefix table, **without spawning any
  agent**.

Exit codes: `0` pass, `1` fail, `2` usage error (bad flags, unknown
subcommand, target not found).

## The fixture runtime (skill-level CI)

`eval/fixture-instance/` is a minimal, vendored instance config
(`identity: DE-EVAL-FIXTURE-001`, `scope: ["acme.demo.eval"]`, empty
`skills.yaml`). Every `triggers`/`safety`/`e2e` run materializes
`eval/fixture-instance/runtime/` by invoking the **real** scaffold builder:

```bash
DE_SCAFFOLD_ROOT=<repo>/scaffold \
  uv run --project scaffold/builder python -m builder.build eval/fixture-instance
```

...then installs the skill-under-test into
`runtime/.claude/skills/<name>/` by direct copy (no `skills.yaml`
registry pin — see Deviations below). The build is cached: a hash of the
skill directory's tree plus `fixture-instance/instance.yaml` is stored in
`.de-eval-fixture-cache.json`; a cache hit skips the rebuild. Pass
`--rebuild-fixture` to force a fresh build.

`scope.service_catalog: ["acme.demo.eval"]` was chosen because the
builder's validator only requires a non-empty list of non-empty strings
(`scaffold/builder/builder/validate.py`) — it does not cross-check against
`mocks/service_catalog.json`, so no real catalog entry was needed.

## Replay strictness (`e2e`)

For each `tests/*.mock.yaml` case:

1. **Shim generation.** One executable shim per distinct first word of
   every fixture's `command_prefix`, plus the fixed deny-set (`curl wget ssh
   kubectl`), written to `eval/runs/<ts>/<case>/shims/`.
2. **Fixture server.** A background thread listens on a unix socket (kept
   in a short system tmpdir — `AF_UNIX` paths are capped around 104 bytes,
   too short for a deep repo checkout's `eval/runs/...` path) and matches
   the shim's reconstructed command string (`basename(argv[0]) + " " +
   " ".join(argv[1:])`) against `fixtures[].command_prefix`,
   **first-match-in-file-order**. A `command_prefix: ""` fixture is a
   fallback (must be last; the runner rejects any fixture that follows it)
   and is served but recorded `"fallback": true`. No match at all -> the
   shim exits `97` and the command is recorded `"matched": false`.
3. **Agent spawn** (skipped under `--dry-run`): `claude -p "<prompt>"
   --output-format stream-json --verbose` with `cwd` = the fixture runtime,
   `PATH=<shims>:$PATH`, `DE_AGENT_PROJECT_DIR=<runtime>`,
   `DE_EVAL_FIXTURE_SOCK=<socket path>`.
4. **Verdict.** Execution axis (`min_replayed_commands`,
   `required_command_substrings`, `forbidden_command_substrings`, and any
   unmatched-command error) is checked in-process from `.commands.jsonl`.
   Result axis (`required_output_semantic_matches`) is graded by the judge
   (§ below), one assertion per `claude -p` call.

Artifacts land under `eval/runs/<UTC-timestamp>/<case-id>/`:
`.commands.jsonl` (one JSON line per shim invocation — the first thing to
check on a failing case), `transcript.jsonl` (the full stream-json
transcript), and `shims/`.

### Manual shim proof (no `claude` involved)

You can drive a shim directly against a running fixture server, e.g. to
verify strict-replay semantics offline:

```bash
uv run --project eval python -m de_eval.fixture_server \
  skills/skills/ticket-review/tests/review-safe-ticket.mock.yaml \
  /tmp/de-eval-demo/fixture.sock \
  /tmp/de-eval-demo/.commands.jsonl
# prints: export DE_EVAL_FIXTURE_SOCK=/tmp/de-eval-demo/fixture.sock

export DE_EVAL_FIXTURE_SOCK=/tmp/de-eval-demo/fixture.sock
/path/to/shims/uv run python scripts/fetch_ticket.py --ticket-id 1001   # matches -> exit 0
/path/to/shims/uv run python scripts/nonexistent.py                    # no fixture -> exit 97 (or fallback if the case has one)
```

Generate a standalone shim dir with:

```python
from pathlib import Path
from de_eval import shim
shim.write_shims(Path("/tmp/de-eval-demo/shims"), {"uv"})
```

## Judge (`eval/judge.toml`)

```toml
[judge]
model = "claude-haiku-4-5"
retry = 1
```

Semantic assertions (`safety`'s `expected_verdict`, `e2e`'s
`required_output_semantic_matches`) are graded by a single non-interactive
`claude -p --model claude-haiku-4-5 --output-format text` call with no
tools, prompted with the assertion, case prompt, full transcript, final
answer, and the skill's `SKILL.md` as rubric context, and instructed to
answer with strict JSON `{"pass": bool, "reason": str}`. One retry on parse
failure or a nonzero exit; retry counts are recorded in the JSON report
(`--report`). Deterministic assertions (substrings, counts, exit codes) are
evaluated in-process and never touch the judge. Changing the judge model
string is a re-baselining event — see
`docs/70-operations/platform-governance.md` §2-3.

## Deviations from eval-spec.md (demo simplifications)

- **Skill install by direct copy.** §5.4 step 5 says the fixture runtime is
  "a real scaffold build ... not a hand-built directory." The build itself
  *is* real (real builder invocation); only the skill-under-test's
  install step bypasses `skills.yaml`/registry resolution and copies the
  skill tree straight into `runtime/.claude/skills/<name>/`. This matches
  the task brief's explicit allowance ("direct copy is fine for the
  fixture").
- **`scope: ["acme.demo.eval"]`** is accepted by the validator (no real
  Service Catalog membership required) — see "The fixture runtime" above.
- **Judge-model pinning for `safety`.** The spec doesn't fully specify how
  `expected_verdict` (DENY / REQUIRE_APPROVAL) is turned into a verdict;
  this harness runs the same agent-spawn mechanism as `triggers` and then
  asks the judge to grade a verdict-specific assertion built from §4.1's
  definitions, giving it the full transcript so a hook-level block and a
  model-level refusal both count as DENY.
- **`lint`'s semver-tag check** validates the `version:` field's format
  (`X.Y.Z`) but does not verify an actual `<skill>/vX.Y.Z` git tag exists —
  this repo's checkout has no tags yet (skill-repo CI's `detect_release.py`
  owns that check separately, per DESIGN.md S4).
- **AF_UNIX socket path.** The fixture socket lives in a short system
  tmpdir (`tempfile.mkdtemp()`) rather than under `eval/runs/<ts>/<case>/`,
  because unix-socket paths are capped (~104 bytes on macOS/BSD) and this
  repo's checkout path routinely exceeds that budget. Every artifact the
  spec actually names (`.commands.jsonl`, `transcript.jsonl`, `shims/`)
  still lives under `eval/runs/<ts>/<case-id>/`.
- **Instance-level `e2e`/`smoke`** (a built `runtime/` directory instead of
  a skill dir, per §6) is not implemented in this pass — this deliverable
  covers the skill-level gates (`lint`/`triggers`/`safety`/`e2e
  <skill-dir>`) exercised by `skills/skills/ticket-review/tests/`.

## Known finding (not a harness bug)

`de-eval lint skills/skills/ticket-review` currently fails: `safety.yaml`
has two `malicious_command` cases (`bypass_audit`, `destructive_command`)
with populated `evaluation.type`/`.label` fields, but
`tests/test-cases.md`'s Evaluation Coverage table has no `malicious_command`
rows at all. Per eval-spec.md §2.6 this is a real coverage gap in the
existing skill fixtures, not a lint false-positive — confirmed by grepping
`tests/test-cases.md` for `malicious_command` (no hits) against
`tests/safety.yaml` (two cases). `skills/` is off-limits for this task, so
the gap is reported here rather than patched.
