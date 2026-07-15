# Cache Scaling Standard Operating Procedure

## Overview

This SOP defines the canonical scaling rules for the checkout and cart service caches. The Acme checkout platform handles peak traffic during promotional campaigns and must maintain performance while optimizing infrastructure costs.

## Scaling Rules

### R1: Memory Utilization Threshold
**Rule**: Memory utilization must stay below 80% at all times.
- **Action**: Scale up cache capacity **before** breaching 80% utilization.
- **Monitoring**: Monitor `acme.storefront.checkout.cache.memory_percent` and `acme.storefront.cart.cache.memory_percent` metrics every 5 minutes.
- **Trigger**: When utilization reaches 75%, initiate scale-up via the Change Gateway.
- **Verification**: After scaling, confirm new utilization is below 70% within 10 minutes.

### R2: Minimum Replica Requirement
**Rule**: Minimum 2 replicas must run at all times for high availability.
- **Requirement**: Both `acme.storefront.checkout.cache` and `acme.storefront.cart.cache` must have >= 2 active replicas.
- **Health Checks**: Verify replica health via `GET /health` endpoint every 30 seconds.
- **Escalation**: If any service drops below 2 replicas, immediately escalate to mentors.

### R3: Post-Campaign Cooldown Window
**Rule**: After a marketing campaign ends, wait 7 days before scaling cache capacity back down.
- **Rationale**: Avoid thrashing due to campaign-end volatility; load patterns stabilize within 7 days.
- **Start Window**: Campaign end time is marked in the Change Gateway event log.
- **Verification**: On day 7, re-evaluate utilization trends before proposing scale-down.
- **Approval Required**: Scale-down proposals must be reviewed by both mentors.

## How to Verify Metrics

1. **Check current metrics** via the Change Gateway mock service:
   ```
   GET http://localhost:8801/metrics/acme.storefront.checkout
   GET http://localhost:8801/metrics/acme.storefront.cart
   ```

2. **Response format**:
   ```json
   {
     "service": "acme.storefront.checkout",
     "cache_replicas": 2,
     "cache_memory_percent": 72.5,
     "cache_connections": 450,
     "updated_at": "2026-07-16T15:30:00Z"
   }
   ```

3. **Trend analysis**: Request the last 24 hours of data to identify scaling patterns:
   ```
   GET http://localhost:8801/metrics/acme.storefront.checkout?hours=24
   ```

## Incident Response

- **R1 Breach**: Immediate scale-up required. Notify both mentors.
- **R2 Breach**: Emergency escalation. Do not wait for Change Gateway approval; contact mentors via email.
- **R3 Violation**: Audit the campaign end date. If cooldown hasn't elapsed, reject the scale-down proposal.

## Related Runbooks

- `checkout-oncall-runbook.md` — Escalation procedures and mentor contacts.
- `service-overview.md` — Service dependencies and ownership.
