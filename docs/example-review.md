# What a review actually looks like

The `ticket-review` skill is deterministic Python (the agent only orchestrates
it). Below are **real, unedited outputs** for the two seeded tickets, produced
by running the skill's scripts against the mock Change Gateway. Both are
comment-only: the digital employee proposes an SOP verdict and routes it to a
human — it never approves or rejects.

## Reproduce it yourself

```bash
# 1. Start the mock Change Gateway
uv run python mocks/change_gateway.py --port 8801 &

# 2. Run the review chain for a ticket (1001 = safe scale-up, 1002 = SOP-violating scale-down)
S=skills/skills/ticket-review/scripts
id=1002
cluster=$(uv run python $S/fetch_ticket.py --ticket-id $id | tee /tmp/t.json | python3 -c "import json,sys;print(json.load(sys.stdin)['cluster'])")
uv run python $S/fetch_metrics.py --cluster "$cluster" --days 7 > /tmp/m.json
uv run python $S/analyze.py --ticket /tmp/t.json --metrics /tmp/m.json > /tmp/a.json
uv run python $S/render_comment.py --analysis /tmp/a.json
```

(In production the agent runs exactly these steps under the skill contract,
gated by the security hooks and strict-replay eval. The `Generated:` line
below reflects the time each sample was produced.)

---

## Ticket 1002 — scale-down that violates the SOP → **FAIL**

This scale-down would drop the cart cluster below the minimum replica count
**and** lands inside the post-campaign cooldown window. The review flags both,
with evidence, and defers the decision to a human:

## Summary

Ticket **1002** (scale_down) on cluster `acme.storefront.checkout.cart` — overall SOP result: **FAIL**. Predicted post-change peak memory utilization: **35.0%**.

## Review Comment

This is an automated SOP check only. It does **not** approve or reject this ticket — a human reviewer makes the final decision.

### Checks

| Rule | Status | Evidence |
|---|---|---|
| predicted_peak_memory_utilization_below_80pct | PASS | 7d observed peak=35.0% on current capacity=32GB (4 nodes x 8GB); target capacity=32GB (4 nodes x 8GB); predicted post-change peak=35.0% (threshold < 80%) |
| minimum_replica_count | FAIL | target replicas=1 (minimum required=2) |
| campaign_cooldown_for_scale_down | FAIL | scale-down requested 2 day(s) after campaign 'mid-year-flash-sale' ended (cooldown=7 days) |

### Verified Inputs

- Ticket ID: `1002`
- Cluster: `acme.storefront.checkout.cart`
- Change type: `scale_down`
- Metrics window: 7-day peak (mock Change Gateway)
- Generated: 2026-07-23 01:09 UTC

### Concerns

- **FAIL** (minimum_replica_count): target replicas=1 (minimum required=2)
- **FAIL** (campaign_cooldown_for_scale_down): scale-down requested 2 day(s) after campaign 'mid-year-flash-sale' ended (cooldown=7 days)

_No approve/reject action was taken. Route this comment to the ticket for human decision._

---

## Ticket 1001 — safe scale-up → **PASS**

## Summary

Ticket **1001** (scale_up) on cluster `acme.storefront.checkout.sessions` — overall SOP result: **PASS**. Predicted post-change peak memory utilization: **54.7%**.

## Review Comment

This is an automated SOP check only. It does **not** approve or reject this ticket — a human reviewer makes the final decision.

### Checks

| Rule | Status | Evidence |
|---|---|---|
| predicted_peak_memory_utilization_below_80pct | PASS | 7d observed peak=82.0% on current capacity=48GB (6 nodes x 8GB); target capacity=72GB (9 nodes x 8GB); predicted post-change peak=54.7% (threshold < 80%) |
| minimum_replica_count | PASS | target replicas=3 (minimum required=2) |
| campaign_cooldown_for_scale_down | PASS | not a scale-down change; rule not applicable |

### Verified Inputs

- Ticket ID: `1001`
- Cluster: `acme.storefront.checkout.sessions`
- Change type: `scale_up`
- Metrics window: 7-day peak (mock Change Gateway)
- Generated: 2026-07-23 01:09 UTC

### Concerns

- None. All SOP checks passed.

_No approve/reject action was taken. Route this comment to the ticket for human decision._
