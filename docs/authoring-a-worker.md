# Author your own intelligent-staff worker

The [README quickstart](../README.md#quickstart-5-minutes) boots the reference
worker (`instances/acme-checkout-sre`). This guide is the next step: standing up
a worker for **your own** team from the same scaffold. Everything below is the
exact flow the reference instance goes through — the commands and their output
are copied verbatim from a fresh build.

A "worker" is an instance directory. The scaffold (`scaffold/`) is the platform;
`de` composes a hardened `runtime/` for each instance from a shared base plus
your `instance.yaml`. You never edit `runtime/` by hand — you edit the spec and
rebuild, and `de diff` proves the two are in sync.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) and `git`.
- An authenticated [`claude` CLI](https://claude.com/claude-code) — only for the
  interactive session (`de start`); `validate` / `build` / `doctor` / `diff` do
  not need it.

## 1. Start from the reference instance

The reference instance is the canonical, tested starting point. Copy it and drop
the generated build artifacts so your first `build` is clean:

```bash
cp -r instances/acme-checkout-sre instances/acme-fulfillment-sre
cd instances/acme-fulfillment-sre
rm -rf runtime editor .build-info.json .managed-files.json .build-manifest.json
```

> **Placement matters.** `base.repo` in `instance.yaml` and the skills registry
> URL in `skills.yaml` are **relative to the instance directory**
> (`file://../../scaffold`, `file://../../skills`). Keeping instances two levels
> below the repo root — `instances/<your-team>/` — makes those resolve. If you
> host instances elsewhere, either make the paths absolute or export
> `DE_SCAFFOLD_ROOT=/abs/path/to/scaffold`.

## 2. Edit `instance.yaml`

This is the whole worker definition. The fields you will almost always change:

```yaml
identity:
  id: DE-ACME-FULFILLMENT-001          # DE-<ORG>-<TEAM>-NNN, a stable functional id
  team: acme-fulfillment-sre
  description: "intelligent-staff worker for the Acme Corp storefront fulfillment SRE team"

scope:
  service_catalog:                     # the services this worker is allowed to reason about
    - acme.storefront.fulfillment
    - acme.storefront.warehouse

escalation:
  enabled: true
  mentor_emails:                       # who gets paged when the worker escalates
    - mentor-one@acme.example
    - mentor-two@acme.example

claude_md:
  extra_rules: |                       # team-specific working protocol, injected into runtime/CLAUDE.md
    ## Change Gateway Policy
    All proposed changes go through the Change Gateway. The worker analyzes and
    proposes; it never executes directly.

bridge:
  enabled: true
  auth:
    allowed_users: ["demo-user", "mentor-one"]
    admin_users:   ["mentor-one"]      # only admins may loosen the permission mode
```

`de validate` accumulates **every** schema error at once (not just the first),
so you can fix a batch in one pass. Full field reference:
`scaffold/builder/builder/validate.py` (schema v1).

## 3. Wire up skills (`skills.yaml`)

Skills are versioned, tag-pinned capabilities the worker can trigger. The
reference worker depends on `ticket-review`:

```yaml
registries:
  local:
    url: "file://../../skills"
default_registry: local
dependencies:
  ticket-review:
    registry: local
    tag: "ticket-review/v0.1.2"        # pinned by tag — reproducible builds
```

Add your own dependency the same way. Skills are released only through the gate
pipeline (`lint → version-check → triggers → safety → e2e → tag`); see
[CONTRIBUTING.md](../CONTRIBUTING.md).

## 4. Load team knowledge (`kb/team/`)

Drop your runbooks, SOPs, and service overviews under `kb/team/` and index them
in `kb/team/_index.md`. They are composed into the worker's runtime knowledge
base so it answers from your operational reality, not generic advice.

## 5. Validate, build, verify

```bash
../../scaffold/de validate .
../../scaffold/de build .
../../scaffold/de doctor .
../../scaffold/de diff .
```

A healthy new worker looks exactly like this:

```
$ de validate .
instance configuration is valid.

$ de build .
build complete: .../instances/acme-fulfillment-sre/runtime

$ de doctor .
[PASS] runtime/ exists
[PASS] required file: CLAUDE.md
[PASS] required file: .claude/policy/security.yaml
[PASS] hook executable: .claude/hooks/skill-gate.py
[PASS] hook executable: .claude/hooks/escalation-guard.py
... (all six security hooks, four policy packs)
[PASS] seeded tests present (5 common guardrail cases)

$ de diff .
no drift: runtime/ matches the last build manifest.
```

`de doctor` confirms the composed runtime carries the full security floor — all
six hooks and four policy packs — so a new worker inherits the same guardrails
as the reference one, for free. `de diff` is the contract that `runtime/` is a
pure function of your spec: if it ever reports drift, someone hand-edited the
runtime, and you rebuild.

Before committing, run the fictional-universe red-line scan (CI enforces it):

```bash
bash scripts/leak-check.sh instances/acme-fulfillment-sre   # -> leak-check: clean
```

## 6. Run it

```bash
# interactive session inside the worker runtime (needs an authenticated claude CLI)
../../scaffold/de start .

# chat bridge (Slack-style front door), from the instance dir
../../scaffold/de serve .

# governance console over the whole fleet, from the repo root
uv run --project console python -m console.app --repo . --port 8900
```

The console will now show your new worker alongside the reference one, with its
own health score, drift status, and draft-based config-change workflow.

## What you did not have to build

Copying one directory and editing one YAML file gave you a worker that already
has: the six-hook security floor (skill-gate, escalation-guard,
context-isolator, injection-detector, input-sanitizer, result-sanitizer), four
policy packs, an escalation path to named mentors, a deterministic and
drift-checked runtime, and a governance console entry. That is the platform's
whole point — the guardrails are the default, not an add-on.
