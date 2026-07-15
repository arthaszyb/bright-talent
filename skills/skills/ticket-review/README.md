# ticket-review (example skill)

A complete, runnable example of a DE skill: reviews Acme Corp cache-cluster
scaling tickets from a bundled mock Change Gateway API and posts a
structured, comment-only SOP review. See `SKILL.md` for the full contract
(triggers, tool allowlist, prohibitions).

This skill never approves or rejects a ticket — it only produces a
pass/warn/fail review comment for a human to act on.

## Layout

```
example-skill/
  SKILL.md                          skill contract
  pyproject.toml                    stdlib-only, python >=3.11
  scripts/
    mock_server.py                  mock Change Gateway (tickets, metrics, comments)
    fetch_ticket.py                 GET /tickets/{id}
    fetch_metrics.py                GET /metrics/{cluster}?days=7
    analyze.py                      SOP rule engine -> checks + summary
    render_comment.py               checks -> final Markdown comment
  tests/
    triggers.yaml                   should/should-not trigger cases
    safety.yaml                     must-be-denied cases
    review-safe-ticket.mock.yaml    e2e: ticket 1001, all-pass
    review-violating-ticket.mock.yaml  e2e: ticket 1002, replica-rule fail
```

## Run it end to end

All commands run from this directory (`docs/30-skills/example-skill/`) using
`uv` — no virtualenv setup needed, stdlib only.

### 1. Start the mock server

```bash
uv run python scripts/mock_server.py --port 8801 &
```

Sanity-check the three endpoints:

```bash
curl -s http://localhost:8801/tickets/1001 | head -c 200
curl -s "http://localhost:8801/metrics/acme.storefront.checkout.sessions?days=7"
curl -s -X POST -H 'Content-Type: application/json' -d '{"body":"test"}' \
  http://localhost:8801/tickets/1001/comments
```

Stop it when done: `kill %1` (or find the PID with `lsof -i :8801`).

### 2. Run the pipeline manually for ticket 1002 (SOP-violating)

```bash
uv run python scripts/fetch_ticket.py --ticket-id 1002 --base-url http://localhost:8801 > /tmp/t.json
uv run python scripts/fetch_metrics.py --cluster acme.storefront.checkout.cart --days 7 --base-url http://localhost:8801 > /tmp/m.json
uv run python scripts/analyze.py --ticket /tmp/t.json --metrics /tmp/m.json > /tmp/a.json
uv run python scripts/render_comment.py --analysis /tmp/a.json
```

Expected: overall **FAIL**, driven by `minimum_replica_count` (target
replicas=1 < minimum 2) and `campaign_cooldown_for_scale_down` (scale-down
requested 2 days after a campaign ended, inside the 7-day cooldown).
`predicted_peak_memory_utilization_below_80pct` still reports PASS (35.0%
predicted) — the ticket fails on the other two rules, not memory.

### 3. Run it for ticket 1001 (safe) and 1003 (borderline)

```bash
uv run python scripts/fetch_ticket.py --ticket-id 1001 --base-url http://localhost:8801 > /tmp/t1.json
uv run python scripts/fetch_metrics.py --cluster acme.storefront.checkout.sessions --days 7 --base-url http://localhost:8801 > /tmp/m1.json
uv run python scripts/analyze.py --ticket /tmp/t1.json --metrics /tmp/m1.json > /tmp/a1.json
uv run python scripts/render_comment.py --analysis /tmp/a1.json
```

Expected: overall **PASS**, all three checks pass (predicted utilization
54.7%, replicas=3, not a scale-down).

```bash
uv run python scripts/fetch_ticket.py --ticket-id 1003 --base-url http://localhost:8801 > /tmp/t3.json
uv run python scripts/fetch_metrics.py --cluster acme.storefront.search.cache --days 7 --base-url http://localhost:8801 > /tmp/m3.json
uv run python scripts/analyze.py --ticket /tmp/t3.json --metrics /tmp/m3.json > /tmp/a3.json
uv run python scripts/render_comment.py --analysis /tmp/a3.json
```

Expected: overall **WARN** — predicted post-change utilization (73.3%) sits
in the 70-79% caution band, just under the 80% fail threshold. Replica and
cooldown checks both pass.

## Verifying the test fixtures

```bash
python3 -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('tests/*.yaml')]"
```

Every file under `tests/` must parse as valid YAML; the `*.mock.yaml` files
additionally follow the `command_replay` schema described in
`40-evaluation/eval-spec.md`.

## Leak check

Run the library-wide leak check over just this skill directory before
committing:

```bash
bash ../../scripts/leak-check.sh .
```
