# Acme Checkout SRE Team Knowledge Base

Welcome to the Acme Checkout SRE team's operational knowledge base. This index links all team runbooks, SOPs, and reference material for the checkout and cart services.

## Essential Reading

### 1. **Service Overview**
- **File**: `service-overview.md`
- **Purpose**: High-level service architecture, team contacts, dependencies, and metrics.
- **Audience**: Everyone working with checkout/cart services.

### 2. **Cache Scaling SOP**
- **File**: `cache-scaling-sop.md`
- **Purpose**: Canonical rules for scaling Redis cache capacity.
- **Contains**: Rules R1 (80% memory threshold), R2 (2+ replicas), R3 (7-day cooldown).
- **Audience**: SREs making scaling decisions; referenced by monitoring alerts.

### 3. **Checkout OnCall Runbook**
- **File**: `checkout-oncall-runbook.md`
- **Purpose**: Escalation procedures, mentor contacts, incident response steps.
- **Contains**: Alert procedures, DE assistant role, cross-team escalation.
- **Audience**: Oncall SREs, mentors, DE assistant (for behavior boundaries).

---

## Quick Links by Role

### For Oncall SREs
1. Read `service-overview.md` to understand what you own.
2. Use `checkout-oncall-runbook.md` for incident response.
3. Refer to `cache-scaling-sop.md` for capacity decisions.

### For DE Assistant
1. Review all three documents to understand scope and constraints.
2. **Key Constraint**: Never approve/reject changes; always propose via the Change Gateway.
3. Follow the three-step protocol: confirm → select skill → propose (never execute).

### For Team Mentors
1. `service-overview.md` — service architecture and team structure.
2. `cache-scaling-sop.md` — scaling rules to enforce.
3. `checkout-oncall-runbook.md` — escalation paths and incident SLAs.

### For Cross-Team Coordination
- See `service-overview.md` for out-of-scope dependencies (payments, logistics).
- Escalate to `acme-payments-sre` for payment gateway issues.
- Escalate to `acme-logistics-sre` for fulfillment issues.

---

## Key Concepts

### The Three-Step Protocol

All work with the DE follows this structure:

1. **Confirm the need** — Clarify what change or analysis is needed.
2. **Select the skill** — Identify which runbook or SOP applies.
3. **Execute the skill** — For changes, propose via Change Gateway; never execute directly.

### Change Gateway (http://localhost:8801)

All proposed changes are submitted to the Change Gateway, which:
- Logs all change events for audit.
- Routes proposals to mentors for approval.
- Prevents unauthorized execution of sensitive operations.

### Rules & Thresholds

| Rule | Threshold | Action |
|------|-----------|--------|
| **R1** | Memory > 80% | Scale up **before** breach |
| **R2** | Replicas < 2 | Immediate escalation |
| **R3** | Campaign end + 7 days | Allowed scale-down cooldown |

---

## Contact Matrix

| Role | Email | Availability |
|------|-------|--------------|
| Mentor (Lead) | mentor-one@acme.example | 24/7 |
| Mentor (Commander) | mentor-two@acme.example | 24/7 |
| Team Oncall | acme-checkout-sre@acme.example | Rotating |
| Team Chat | #acme-checkout-sre | During business hours |

---

## Related Documentation

- **Acme Checkout SRE Instance**: `/docs/20-instance/instance-yaml-spec.md` (schema reference)
- **Scaffold Design**: `/docs/10-scaffold/design.md` (platform architecture)
- **DE Roles & Responsibilities**: `/docs/20-instance/design.md` (governance)

---

## Document Versions

- **Last Updated**: 2026-07-16
- **SOP Version**: 1.0
- **Team**: acme-checkout-sre
- **Instance ID**: DE-ACME-CHECKOUT-001
