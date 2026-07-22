# Service Overview: Acme Checkout & Cart

## Team Information

**Owner Team**: `acme-checkout-sre`  
**Oncall**: `acme-checkout-sre@acme.example`  
**Mentors**: `mentor-one@acme.example`, `mentor-two@acme.example`

---

## In-Scope Services

### 1. acme.storefront.checkout

**Purpose**: Checkout service handling payment processing and order finalization.

**Responsibilities**:
- Accept order submission from cart
- Process payment authorization via payments gateway
- Generate order confirmation
- Initiate fulfillment workflow with logistics team

**Dependencies**:
- **acme.storefront.cart** (upstream) — order composition
- **acme.storefront.payments** (external) — payment processing
- **acme.logistics.warehouse** (downstream) — order fulfillment

**Tech Stack**:
- Language: Go
- Framework: gRPC
- Cache: Redis (2+ replicas, target < 80% memory)
- Database: PostgreSQL (primary + read replica)

**Key Metrics**:
- `checkout_orders_per_minute` — throughput
- `checkout_error_rate_5m` — success rate
- `cache_memory_percent` — resource utilization
- `p99_latency_ms` — response time SLO (< 500ms)

---

### 2. acme.storefront.cart

**Purpose**: Shopping cart service for item management and checkout workflow.

**Responsibilities**:
- Maintain user shopping cart state
- Apply discounts and promotions
- Calculate shipping estimates
- Hand off to checkout service

**Dependencies**:
- **acme.storefront.search** (read-only) — product catalog lookups
- **acme.storefront.checkout** (downstream) — order submission

**Tech Stack**:
- Language: Python
- Framework: FastAPI
- Cache: Redis (2+ replicas, target < 80% memory)
- Database: DynamoDB (eventually consistent)

**Key Metrics**:
- `cart_items_per_session` — average cart size
- `cart_abandonment_rate` — business metric
- `cache_memory_percent` — resource utilization
- `p95_latency_ms` — response time SLO (< 200ms)

---

## Out-of-Scope Services

The following services are **not** owned by acme-checkout-sre and are out of scope for this intelligent-staff instance:

- **acme.storefront.search** (owned by acme-search-sre)
- **acme.storefront.payments** (owned by acme-payments-sre)
- **acme.logistics.warehouse** (owned by acme-logistics-sre)
- **acme.logistics.shipping** (owned by acme-logistics-sre)
- **acme.logistics.tracking** (owned by acme-logistics-sre)

For incidents involving these services, escalate to their respective oncall teams.

---

## Service Dependencies Graph

```
┌─────────────────┐
│  Search Srv     │ ◄─── acme-search-sre (out-of-scope)
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  Cart Service           │ ◄─── acme-checkout-sre (IN-SCOPE)
│  (acme.storefront.cart) │
└────────┬────────────────┘
         │
         ▼
┌────────────────────────────┐
│  Checkout Service          │ ◄─── acme-checkout-sre (IN-SCOPE)
│  (acme.storefront.checkout)│
└────────┬───────────┬───────┘
         │           │
         ▼           ▼
    ┌────────┐   ┌──────────────┐
    │Payments│   │ Logistics    │ ◄─── acme-logistics-sre (out-of-scope)
    │  Srv   │   │ (warehouse)  │
    └────────┘   └──────────────┘
```

---

## Operations Handbook

For detailed procedures, see:

- **Cache Scaling**: `cache-scaling-sop.md` — Rules R1, R2, R3 for scaling decisions.
- **Escalation Path**: `checkout-oncall-runbook.md` — Incident response and mentor contacts.
- **Change Management**: All changes proposed via the Change Gateway at http://localhost:8801.

---

## Quick Facts

| Aspect | Value |
|--------|-------|
| **Team Size** | 4 SREs |
| **24/7 Coverage** | Yes (rotating oncall) |
| **Runbook Index** | `kb/team/_index.md` |
| **Mentor Escalation** | 24/7 via email |
| **Change Review SLA** | 10 minutes (non-critical), immediate (critical) |

