# de-demo Global Design — Component Boundaries, Seam Contracts, Execution Plan

Status: architect-reviewed after wave 1 (M0 mocks, M1 hooks/policies, M1 templates/kb/seeds all delivered and verified).
This document is the binding integration design. `ARCHITECTURE.md` fixes layout/conventions; this file fixes **who owns what, what crosses each boundary, and in what order we build**. Specs remain authoritative in `../docs/`; where the demo deviates, the deviation is registered here (§4) and must be echoed in the final README governance answers.

---

## 1. Layer → component mapping and responsibility matrix

| Layer (docs/00-overview) | Demo component | Owns | Must never do |
|---|---|---|---|
| ACCESS | `bridge/` + `mocks/chat_client.py` | webhook auth, session lifecycle, memory injection | interpret policy; touch instance repos |
| RUNTIME | `instances/acme-checkout-sre/` | declarative intent (`instance.yaml`, `skills.yaml`, `kb/team/`, tests) | hand-edit `runtime/` (build artifact) |
| PLATFORM | `scaffold/` (base + templates + builder + `de`) | security floor, composition, build determinism | let instance shadow base files or relax permissions |
| SUPPLY | `skills/` repo + `eval/` harness | versioned capabilities + release gates | grant skills write credentials |
| EXECUTION | `mocks/change_gateway.py` | the only "write path" (ticket comments), human-approval fiction | be bypassed: no other component writes anywhere external |
| Governance (cross-cut) | `console/` | read-model over the fleet + draft workflow via `./de` | become a second source of truth; edit instance trees in place |

## 2. Seam contracts (load-bearing; every dispatched task must conform)

### S1. `de` CLI ↔ builder
- Invocation: `uv run --project "$SCAFFOLD_ROOT/builder" python -m builder.<mod> <instance_root> [flags]` where `<mod>` ∈ `validate|build|diff|doctor|status`.
- Builder raises typed errors (`ValidationError`, `BuildConflictError`, `MonotonicityError`) → non-zero exit with bulleted, field-level messages on stderr; `de` maps: builder non-zero → exit 1; unknown flag/subcommand → exit 2; success → 0.
- `de init <dir>` is pure bash: stamps `scaffold/templates/instance/` + copies managed files (`de`, `Makefile`) and records them in `.managed-files.json` (see S2).

### S2. Build artifacts (produced by builder, consumed by eval/bridge/console)
- `<instance_root>/.build-manifest.json` — `{files: [{path, sha256, source: base|template|instance|seed}]}` (paths relative to `runtime/`). Consumed by `de diff` (drift) and console (drift panel). *(W2 as-built: artifacts live at instance root, not under runtime/; entry is a list with `source` per file.)*
- `<instance_root>/.build-info.json` — flat summary: `instance_identity`, `scaffold_version`, `built_at`, `claude_cli_version` (from `claude --version` at build time; governance §1 pin rule). *(W2 as-built: scope/skills live in `.managed/skills-lock` + rendered CLAUDE.md, not duplicated here; consumers needing scope read instance.yaml.)* Consumed by eval smoke and console.
- `<instance_root>/.managed-files.json` — `{files: [{path, template_sha256, synced_at, scaffold_version}]}`, committed. Written by builder/init on every managed-file sync; consumed by console's `both_changed` conflict detection. **New requirement surfaced by console spec — builder task must include it.**
- Build runs twice: `runtime/` (full) and `editor/` (restricted: editor-CLAUDE.md, no ops skills).

### S3. Runtime layout (consumed by claude CLI, hooks, eval, bridge)
- `runtime/` = Claude Code project dir: `CLAUDE.md`, `.claude/{settings.json, hooks/, policy/, tools/, skills/}`, `kb/`, `work/` (gitignored hook state), `.mcp.json`.
- Env floor exported by every launcher (`de start`, `de serve`, `de-eval`): `DE_AGENT_PROJECT_DIR=<abs runtime>`, `DE_SCOPE_SERVICE_CATALOG=<comma-joined scope>`, plus `.env` if present. Hooks resolve all state through `DE_AGENT_PROJECT_DIR` (verified in wave 1).
- Skills are installed under `.claude/skills/<name>/` from the lock file; the `Skill` tool + skill-gate hook enforce skill-first execution.

### S4. Skills registry (demo form)
- `skills.yaml`: `registries: {local: {url: "file://../../skills"}}`, `default_registry: local`, `dependencies: {ticket-review: {registry: local, tag: "ticket-review/v0.1.0"}}`.
- Resolution: `file://` registry = local git repo; resolve tag→commit via `git -C <path> rev-parse`; `skills-lock.json`: `{skills: {<name>: {version, commit, integrity: sha256-of-tree, path}}}`. No network ever.
- Skill repo CI gates are plain scripts under `skills/ci/` (`detect_release.py`, `lint.py`, `version_check.py`) callable locally (`uv run`) and from `.github/workflows/skills-ci.yml`; triggers/safety/e2e gates shell out to `de-eval` (S5).

### S5. Eval harness (`eval/`, command `de-eval`)
- Subcommands: `lint|triggers|safety|e2e <skill-dir|runtime-dir>`; exit 0 pass / 1 fail / 2 usage. Batch flags: `--cases <glob>`, `--report <json path>`.
- Judge pin: `eval/judge.toml` → `[judge] model = "claude-haiku-4-5"`; judged assertions retried at most once (recorded in report), per governance §3.
- e2e PATH-shim: shims for first words of fixture `command_prefix` + deny-set (`curl wget ssh kubectl`); unix-socket fixture server; first-match-in-file-order; unmatched → shim exit 97 + case fails; `""` fallback recorded `"fallback": true`. Artifacts per case: `.commands.jsonl`, `transcript.jsonl` under `eval/runs/<ts>/<case>/`.
- Skill-level runs use a **fixture runtime** (identity `DE-EVAL-FIXTURE-001`, scope `["acme.demo.eval"]`) materialized by calling the real scaffold builder against a vendored fixture instance config in `eval/fixture-instance/` — eval never re-implements the build.
- Trigger detection = presence of `Skill` tool_use for the target skill in stream-json transcript.

### S6. Bridge (`bridge/`)
- `./de serve` renders `bridge.yaml.j2` → `<instance>/log/bridge-config.yaml` (secrets as env refs), then `uv run --project "$SCAFFOLD_ROOT/../bridge" python -m bridge.app --config <path>`; PID at `log/bridge-http.pid`.
- Wire contract (mock chat ↔ bridge): POST `/webhook/events`, header `X-Chat-Signature = hex(HMAC-SHA256(signing_secret, raw_body))`, constant-time compare before parse; `verification` event echoes challenge synchronously; all else 200 within 5s + background handling.
- Session key `channel:thread` → persistent `claude --output-format stream-json --input-format stream-json --verbose --permission-mode <mode>` subprocess with cwd = runtime snapshot, env floor per S3; `sessions.json` v4; resume via `--resume <session_id>`.
- Demo simplifications: dream service = config keys + no-op stub with logged skip reason; relay mode not implemented (config validation rejects it with a clear message).

### S7. Console (`console/`)
- Backend FastAPI + SQLite (tables `drafts`, `audit_events`, `skill_snapshots` — columns/indexes per docs/60-console spec); frontend = static React SPA served by the backend (no SSR, no build pipeline beyond `npm run build` — or a prebuilt vanilla-React setup via CDN if node absent; decide at dispatch by probing environment).
- Reads: scans `instances/*` read-only (git worktree state, `.managed-files.json`, `.build-manifest.json`); **mock CI provider** returns `available: true, steps: all pass` for any instance bearing the managed workflow file (else every clean instance scores `risk` — spec's explicit demo note); **mock MR provider** records MRs as rows + local branches, no remote.
- Writes: draft workflow only — clone instance into `console/workspaces/<draft>/`, apply op, `git diff`, allowlist check (op-type table + always-forbidden set `runtime/ .env* .claude/policy/ .claude/hooks/`), `./de validate`, `./de build`, mock-MR. Never touches the real instance tree; every transition → `audit_events` row.
- Health score & 4-state status: implement exactly the spec's deduction/precedence tables (copied into the dispatch brief; no reinterpretation).

## 3. Wave-1 integration fixes (owned by wave-2 builder task)
1. `templates/settings.json.j2`: remove non-existent keys (`version`, `workingDirectory`); rewrite permission rules in valid Claude Code syntax (`Bash(rm -rf:*)` prefix form; no `*|…` pseudo-globs; deny `Edit` on `.claude/**`, `CLAUDE.md`, `settings.json` via supported path patterns); keep hook wiring as-is (verified correct shape).
2. `templates/mcp.json.j2`: escalation server launched via `python3` is acceptable (stdlib-only) but path must be `$CLAUDE_PROJECT_DIR/.claude/tools/de-agent-escalate.py` — verify template var actually renders an absolute-safe path at build time.
3. skill-gate flag semantics: flag set at PreToolUse of `Skill` (before the call succeeds) — accepted demo tolerance; document in deviation register.
4. Hooks use `#!/usr/bin/env python3` (stdlib-only) — accepted exception to the "uv only" rule; document.

## 4. Deviation register (demo vs. spec — feeds README governance §7)
| # | Deviation | Class |
|---|---|---|
| D1 | Base/skills fetched from local paths (`file://`), no remote repos or tags on a forge; auto-tag CI simulated by local scripts + real git tags in `skills/` | simplified-for-demo |
| D2 | Instance Manager absent: deploy = local `./de build && ./de serve`; console `deploy/refresh` reads local state | simplified-for-demo |
| D3 | Bridge relay mode, dream consolidation, working-card UI: config-recognized but stubbed | simplified-for-demo |
| D4 | Console MR/CI providers are mocks (SQLite rows + local branches) | simplified-for-demo |
| D5 | Transcript shipping to append-only external storage, retention, access control | deferred-with-note |
| D6 | Per-instance service accounts / secret store: `.env` + placeholders only | deferred-with-note |
| D7 | CLI/model pinned by recording versions in `.build-info.json`; no canary fleet | simplified-for-demo |
| D8 | skill-gate flag set on Skill PreToolUse (not post-success); hooks via system python3 (stdlib) | simplified-for-demo |

## 5. Risk register and mitigations
| Risk | Where | Mitigation |
|---|---|---|
| Claude Code settings/hook schema drift vs docs' assumptions | M1/M2 live | Harness contract probe script `scaffold/base/contract-test.sh` (hooks stdin/exit-2, env propagation) run in `de doctor`; fix templates, not hooks |
| Live trigger tests flaky (model routing) | M3/M4 | thresholds per spec (0.9); judge retry-once policy; failures analyzed by Fable before any re-dispatch |
| PATH-shim misses shell builtins/abs paths | M4 | spec-acknowledged limitation; assert only on fixture-covered commands; deny-set for network binaries |
| stream-json protocol details (control_request ack, session_id timing) | M5 | build a 20-line protocol probe first inside the M5 task; code against observed frames |
| Console scope creep (full spec is huge) | M6 | dispatch brief pins: catalog + instance page + CONFIG_EDIT draft type only; other op types = enum + allowlist table present but UI-exposed only for CONFIG_EDIT |
| Cross-agent file collisions | all | one writer per directory per wave; Fable is the only integrator touching shared files |
| Token burn on retries | all | Fable diagnoses failures first; sub-agents get diffs-to-apply, never "figure it out" |

## 6. Execution waves (dependency-safe dispatch plan)
- **W1 (done):** M0 mocks · M1 hooks/policies · M1 templates/kb/seeds — verified.
- **W2 (next, 1 sonnet):** builder package + `de` CLI + §3 fixes + fixture instance for self-test. Accept: full M1 checklist (validate fail/pass, fixture build w/ manifest, BuildConflictError, monotonicity, probe exit 2) + `.managed-files.json` emitted.
- **W3 (1 haiku):** M2 instance files (identity/scope/kb SOP/.env.example) → offline accept (`build/doctor/status/diff`).
- **W4 (parallel):** M3a haiku port of ticket-review into `skills/` + git tags; M3b sonnet CI gate scripts + Actions YAML. Offline accept: detect-release / lint dry-runs.
- **W5 (1 sonnet):** M4 `de-eval` (biggest single task; PATH-shim + judge + fixture runtime). Offline accept: lint on ticket-review.
- **LIVE BATCH A (Fable):** M2 scope Q + M3 trigger/review e2e + M4 `de-eval triggers/e2e/smoke` + strict-replay two-part proof — one sitting, mocks up.
- **W6 (parallel):** M5a sonnet bridge; M5b haiku chat client. **LIVE BATCH B:** bridge conversations/isolation/auth.
- **W7 (sonnet):** M6 console backend+frontend. **LIVE BATCH C (final gate):** leak-check full tree, fresh e2e conversation, README governance answers (Fable-authored from §4).
- Commit after each accepted milestone (leak-check first), per plan.
