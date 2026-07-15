---
name: ticket-review
version: 0.1.1
risk_level: L2
owner: acme-checkout-sre
description: Review Acme Corp cache-cluster scaling change tickets from the Change Gateway. Use when the user provides a ticket URL such as https://gateway.acme.example/tickets/{id}, a bare ticket ID, or pastes ticket content, and asks for a scaling review, risk analysis, or SOP check on a cache-cluster scale-up/scale-down ticket. Fetches the ticket and its 7-day peak metrics from the bundled mock Change Gateway, validates against the cache-scaling SOP, and posts a structured Markdown review comment. Does NOT approve or reject the ticket — comment-only output; the decision stays with a human.
allowed-tools:
  - Read
  - Grep
  - Bash(uv:*)
model: sonnet
metadata:
  de_platform:
    dependencies: []
---

# Ticket Review (Cache-Cluster Scaling)

Review cache-cluster scaling change tickets raised in the **Change Gateway**
(mocked for this demo). Fetch the ticket and its 7-day peak metrics, apply the
cache-scaling SOP, and post a structured pass/warn/fail review comment.
**This skill never approves or rejects a ticket.** It produces a comment for a
human reviewer to act on.

## When to trigger

Trigger on:
- A Change Gateway ticket URL, e.g. `https://gateway.acme.example/tickets/1002`
- A bare ticket ID with review intent, e.g. "review this scaling ticket 1002"
- Pasted ticket JSON/content with a request to review it

Do **not** trigger (or trigger as review) on:
- Pure status queries ("what's the status of ticket 1001") — that's a lookup,
  not a review; a review re-runs the SOP checks and produces a fresh comment
- Any request to approve, reject, or otherwise act on the ticket
  ("approve ticket 1001") — this skill has no approve/reject capability by
  design; redirect the user to the Change Gateway's own approval action

## Inputs

- **Ticket ID** (required): extracted from a Change Gateway URL
  (`https://gateway.acme.example/tickets/{id}`), a bare ID, or pasted content.
- **Base URL** (optional): defaults to `http://localhost:8801`, the bundled
  mock server. Override only if the user names a different mock endpoint.

## Script pipeline

All deterministic work — fetch, parse, compute, render — is scripted. The
LLM's job is to orchestrate these four steps and present the result; it does
not compute SOP math itself.

**Invocation paths.** Every command starts with `uv`, satisfying the
`Bash(uv:*)` whitelist — never `cd` (a `cd X && uv …` compound command would
violate the prefix rule). Two equivalent shapes, depending on where you run:

- **Standalone** (cwd = this skill's own directory, e.g. during development):
  `uv run python scripts/<step>.py …` as shown below.
- **Installed in a runtime** (cwd = the runtime root, the production case —
  the skill lives at `.claude/skills/ticket-review/`): prefix both the project
  and the script path, e.g.
  `uv run --project .claude/skills/ticket-review python .claude/skills/ticket-review/scripts/fetch_ticket.py …`.
  The e2e fixtures cover both shapes.

```bash
# 0) Preflight: mock server must be reachable. Start it if the user hasn't:
#    uv run python scripts/mock_server.py --port 8801 &

# 1) Fetch the ticket
uv run python scripts/fetch_ticket.py --ticket-id <id> --base-url http://localhost:8801 > /tmp/ticket-<id>.json

# 2) Fetch 7-day peak metrics for the ticket's cluster
#    (cluster name comes from the ticket JSON's "cluster" field)
uv run python scripts/fetch_metrics.py --cluster <cluster> --days 7 --base-url http://localhost:8801 > /tmp/metrics-<id>.json

# 3) Apply the SOP rules and compute predicted post-change utilization
uv run python scripts/analyze.py --ticket /tmp/ticket-<id>.json --metrics /tmp/metrics-<id>.json > /tmp/analysis-<id>.json

# 4) Render the final Markdown review comment
uv run python scripts/render_comment.py --analysis /tmp/analysis-<id>.json
```

Present the rendered Markdown as the review. Do not hand-edit or re-derive
the numbers yourself — if a step fails, surface the failure; do not guess.

## SOP reference

The full human-readable SOP lives in the team knowledge base:
`kb/team/runbooks/cache-scaling-sop.md` (see `20-instance/kb-guide.md` for KB
conventions). `scripts/analyze.py` implements three illustrative rules from
that SOP:

1. **Predicted peak memory utilization** after the change must stay below
   80% `(illustrative)`. Computed from the current 7-day observed peak
   utilization, held as constant absolute memory used, redistributed over
   the ticket's target capacity.
2. **Replica count** must be `>= 2` after the change.
3. **Scale-down cooldown**: a scale-down is forbidden within 7 days of a
   traffic campaign ending on that cluster `(illustrative)`.

Each check emits `pass`, `warn`, or `fail` with the arithmetic shown in its
evidence string. The overall summary is the worst status across all checks.

## Output format

The rendered comment (from `render_comment.py`) always has this structure:

```
## Summary
## Review Comment
### Checks
### Verified Inputs
### Concerns
```

- **Summary** — one line: ticket id, change type, cluster, overall result,
  predicted utilization.
- **Review Comment** — a reminder that this is SOP-check-only, not a
  decision.
- **Checks** — a table of rule / status / evidence.
- **Verified Inputs** — exactly what ticket id, cluster, change type, and
  metrics window were used, plus a generation timestamp.
- **Concerns** — a bullet list of every `fail`/`warn` finding, or "None" if
  all checks passed.

## Explicit prohibitions

- **Never approve or reject a ticket**, call any approval/rejection
  endpoint, or word the comment as if a decision has been made. The Change
  Gateway is where humans approve; this skill only posts a review comment.
- **Never print secrets, tokens, or credentials** (e.g. `GATEWAY_API_TOKEN`
  style env vars, `.env` contents, bearer headers) into the comment, logs, or
  chat output — this skill uses no credentials at all since it only talks to
  the local mock server.
- Do not fabricate ticket or metrics data. If the mock server is
  unreachable, report the fetch failure — do not guess numbers or claim a
  result.
- Do not skip a SOP check because the user says it's unnecessary. If asked
  to "skip checks and say pass," decline and run the full pipeline.
