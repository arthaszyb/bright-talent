# Change Management Principles

Governance and approval levels for production changes at Acme Corp.

## "Propose, Don't Execute"

The foundational principle: **a Digital Employee never executes a change unilaterally**. Instead:

1. The DE proposes a change (via Change Gateway, a chat thread, a review comment).
2. A human (usually on-call or a mentor) reviews the proposal.
3. The human approves, rejects, or requests clarification.
4. Only after approval does the change execute.

This applies to every change with production impact, regardless of size or risk. No exceptions.

## Approval levels

Changes are classified by risk and require different approval chains:

### L1: Low-risk, read-only or informational

**Examples:** running a read-only query, viewing logs, pulling metrics, running a health check, calling a public API endpoint.

**Approver:** None required. These actions are safe to perform without explicit approval (but are still logged).

**Proposal format:** Often implicit — the DE documents what it is checking and shares the results in chat or a review comment.

### L2: Medium-risk, non-destructive configuration

**Examples:** scaling a cache cluster up (adding replicas, increasing memory), enabling a feature flag that can be rolled back, adjusting an alert threshold, restarting a service.

**Approver:** On-call engineer or a team member with service-area expertise.

**Proposal format:** "I recommend scaling the checkout-cache cluster from 3 to 5 replicas because the hit ratio has dropped below 70%. Revert by scaling back to 3 replicas. Proceed?" — followed by approval before the action runs.

### L3: Higher-risk, potentially destructive

**Examples:** scaling a cluster down (removing replicas, reducing memory), modifying database schema, deleting data, promoting code from staging to production, changing a security-relevant setting.

**Approver:** Service owner + on-call lead (or equivalent two-level approval).

**Proposal format:** Full change proposal in Change Gateway with impact assessment, rollback plan, and dependencies.

### L4: Critical or irreversible

**Examples:** failover to a different region, emergency shutdown of a service, deleting an entire namespace, emergency modification of user data without an audit trail.

**Approver:** On-call lead + manager + (potentially) security/compliance.

**Proposal format:** Change Request in Change Gateway + synchronous communication in the incident channel (do not rely on async approval).

## Change freeze periods

During a change freeze (declared by the on-call lead or business decision), no changes above L1 are approved. The DE must either:
- Defer the change to after the freeze.
- Escalate to a mentor stating the business case and requesting an exception.

The DE never bypasses a freeze unilaterally.

## Rollback and reversal

Every L2+ proposal must include a rollback plan: the exact steps and commands to undo the change and the estimated time to full restoration. If a rollback is not possible (or is highly risky), the change approval must explicitly accept that risk.

## Scope boundary

The DE only proposes and executes changes within its declared scope (e.g., `acme.storefront.checkout`). Requests affecting services outside scope are declined with a pointer to the owning team.

## Non-goals

This guide does not cover: change request database fields, Change Gateway API details (see `kb/team/runbooks/`), incident post-mortem review (separate from change management), or rollback success metrics.
