# access-review

A second reference skill for the intelligent-staff platform, alongside
[`ticket-review`](../ticket-review/). Where `ticket-review` is an SRE
capacity-change worker, `access-review` is a **security/compliance** worker —
demonstrating that the same scaffold, security floor, and eval harness carry a
different kind of digital worker unchanged.

It reviews a service **access-grant request** against the Acme Corp
least-privilege access policy and posts a structured, comment-only review. It
**never grants, approves, or revokes access** — the decision stays with a human
approver, exactly like `ticket-review` never approves a change.

## What it checks

Against the bundled machine-readable policy (`policy/access-policy.json`; the
human-readable version lives in the team KB):

1. **Role in catalog** — the requested role must exist in the target service's
   role catalog. Unknown / over-broad roles fail.
2. **Production time-boxing** — a production grant must cite a justification
   ticket and be time-boxed to ≤ `max_prod_grant_days` (default 90). No
   standing production access.
3. **Privileged PII needs manager approval** — a privileged role
   (`operator`/`admin`) on a PII-classified service in production requires
   `manager_approved: true`.

Each check emits `pass`/`warn`/`fail` with its reasoning; the summary is the
worst status.

## Try it

```bash
cd skills/skills/access-review

# A compliant production admin grant (ticketed, time-boxed, manager-approved) → PASS
echo '{"request_id":"AR-2043","requestor":"jordan@acme.example","service":"acme.storefront.checkout","role":"admin","environment":"production","justification_ticket":"OPS-1187","duration_days":30,"manager_approved":true}' \
  | uv run python scripts/analyze_request.py --request - \
  | uv run python scripts/render_review.py --analysis -

# A standing prod admin grant with no ticket and no manager approval → FAIL
echo '{"request_id":"AR-2044","requestor":"dev-sam@acme.example","service":"acme.storefront.payments","role":"admin","environment":"production"}' \
  | uv run python scripts/analyze_request.py --request - \
  | uv run python scripts/render_review.py --analysis -
```

## Release

Released through the same gated pipeline as every skill
(`detect-release → lint → version-check → triggers → safety → e2e → tag`); see
the repository `CONTRIBUTING.md` and `skills/ci/`.
