# Staff Fleet Governance Console

A read-mostly governance UI over the intelligent-staff worker demo fleet (`instances/*`), plus a
change-draft workflow that never writes to a real instance's working tree.

Backend: FastAPI + SQLite. Frontend: a single-page app in plain HTML/CSS/JS
(no build step, no CDN, no npm — everything is vendored/inline).

## Quickstart

From the `de-demo` repo root:

```bash
uv sync --project console --extra dev
uv run --project console python -m console.app --repo . --port 8900
```

Then open `http://127.0.0.1:8900/`.

- `--repo` is the path to the `de-demo` root (the directory containing
  `instances/`, `scaffold/`, `skills/`).
- `--port` defaults to `8900` (never `8801`/`9100` — those are the Change
  Gateway and chat mocks; see `../ARCHITECTURE.md`).
- The SQLite database lives at `console/data/console.db` by default
  (override with `--db-path`).
- Draft validate/build-test runs happen in throwaway temp directories under
  `console/workspaces/` — safe to delete at any time; the app recreates them
  as needed and removes each one after its validate/build-test call.

Run the test suite:

```bash
uv run --project console --extra dev pytest console/tests -q
```

## What's real vs. mocked

- **Real**: the repo scan (`instances/*/instance.yaml`, `VERSION`,
  `.build-info.json`, `.managed-files.json`, `.build-manifest.json`), the
  health-score/status computation, and the draft workflow's `./de validate`
  / `./de build` calls (these run the actual scaffold builder against a
  temp copy of the instance).
- **Mocked** (`console/console/providers.py`, per de-demo/DESIGN.md §S7/D4):
  - **CI**: no real CI system runs anywhere in this demo. `MockCIProvider`
    treats an instance as CI-available if its `Makefile` is present — the
    `Makefile`'s `verify` target (`de validate && de build`) is this demo's
    actual local CI entry point, since no `.github/workflows/instance-ci.yml`
    is ever produced by the build pipeline in this fictional universe (see
    `DESIGN.md` §S2). All declared steps report `pass`. For the skills repo,
    CI availability is checked literally against the `skills-ci.yml`
    workflow (repo root `.github/workflows/`, with the legacy in-tree
    `skills/.github/` location also accepted).
  - **MR**: "creating an MR" inserts a `drafts` row and creates a local git
    branch `console/draft-<id>` in the de-demo repo — nothing is pushed
    anywhere, no network call is made.

## Demo scope

Per de-demo/DESIGN.md §5 (risk register: "console scope creep"), this build
exposes only the `CONFIG_EDIT` operation type in the UI/API create-draft
path. `SKILL_ADD`/`SKILL_REMOVE`/`SKILL_UPDATE`/`SCAFFOLD_UPGRADE`/`ROLLBACK`
are recognized in the allowlist table (`console/console/drafts.py`) but
rejected by `create_draft` for this build. `CONFIG_EDIT` may touch:
`instance.yaml`, `skills.yaml`, `.gitignore`, `.env.example`, `README.md`,
and anything under `kb/team/`. Everything under `runtime/`, real `.env*`
files, `.claude/policy/`, `.claude/hooks/`, `commands/`, `agents/`, and
`tools/` is always rejected, regardless of operation type.

## Draft state machine

```
DRAFT --validate--> VALIDATING --> VALIDATED --(fail)--> DRAFT
VALIDATED --build-test--> BUILD_TESTING --> BUILD_TESTED --(fail)--> DRAFT
BUILD_TESTED --create-mr--> MR_CREATED
```

Every transition writes a row to `audit_events`. Validate and build-test copy
the real instance directory (minus `runtime/` and `editor/`, the build
outputs) into an isolated temp workspace, apply the draft's pending file
edits there, rewrite the workspace-relative `file://../../{scaffold,skills}`
registry URLs to absolute paths (so `./de` resolves the local skill/scaffold
registries regardless of where the temp workspace lives), and run
`<repo>/scaffold/de validate|build .` inside that workspace only. The real
`instances/<id>/` tree is never touched by a draft.

## Demo walkthrough

1. Open the console, land on the **Fleet** tab — `acme-checkout-sre` shows a
   health score and status badge.
2. Click into it to see the drift table (managed files vs. the scaffold),
   installed skills, and mock CI status.
3. Click **+ New CONFIG_EDIT draft**, add a file under `kb/team/` (e.g.
   append a line to `kb/team/_index.md`), and **Save files**.
4. Click **Validate** → **Build-test** → **Create MR**, watching the state
   badge advance through `DRAFT → VALIDATING → VALIDATED → BUILD_TESTING →
   BUILD_TESTED → MR_CREATED`.
5. Check the **Audit Log** tab — every transition above has a row.
6. Back on the instance page, the real `instances/acme-checkout-sre/kb`
   files are unchanged; only the temp workspace (already deleted) and the
   `console/draft-<id>` git branch reflect the change.

## Spec simplifications (this build)

- The design doc's fuller `MATERIALIZING/DIFF_READY/CI_RUNNING/...` state
  machine is collapsed to the task brief's five states
  (`DRAFT/VALIDATING/VALIDATED/BUILD_TESTED/MR_CREATED`); failures return to
  `DRAFT` uniformly rather than to the nearest prior success state.
- Three-way managed-file conflict detection (`both_changed`) is only
  possible for managed files that are literal copies of
  `scaffold/base/<path>` (manifest `source: "base"`); files rendered from a
  Jinja template (`source: "template"`, e.g. `CLAUDE.md`, `.claude/settings.json`)
  fall back to a two-way comparison (recorded-sync-hash vs. current local
  hash) since the scanner does not reimplement the builder's templating.
- CONFIG_EDIT's allowlist is the task brief's wider table (adds
  `kb/team/**`, `.env.example`, `README.md`, `skills.yaml` beyond the design
  doc's bare `.gitignore`/`instance.yaml` pair) — a documented widening, not
  a narrowing, of the spec.
- Skill-snapshot DB caching (design doc §"skill_snapshots" / 5-minute sync
  job) is implemented as the `skill_snapshots` table shape only; `/api/skills`
  computes its response live from the repo scan rather than running a
  background sync loop, since the demo fleet is a single instance.
