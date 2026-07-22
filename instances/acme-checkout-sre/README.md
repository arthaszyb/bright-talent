# Acme Checkout SRE — Intelligent Staff Instance

This is the configuration repository for the **DE-ACME-CHECKOUT-001** intelligent-staff instance, serving the Acme Checkout SRE team.

## What This Instance Does

The DE-ACME-CHECKOUT-001 assistant provides:

- **Scope**: Expertise in `acme.storefront.checkout` and `acme.storefront.cart` services
- **Role**: SRE assistant for diagnostic analysis, incident triage, and change proposals
- **Skills**: Cache scaling decisions, incident response runbooks, service dependency analysis
- **Constraints**: All changes proposed via the Change Gateway; no direct execution
- **Mentors**: mentor-one@acme.example, mentor-two@acme.example

---

## Quick Start

### 1. Validate Configuration
```bash
cd instances/acme-checkout-sre   # from the de-demo repo root
../../scaffold/de validate .
```
Expected: Exit code 0, no errors.

### 2. Build the Runtime
```bash
../../scaffold/de build .
```
Expected: Exit code 0; creates `runtime/` directory with compiled config and KB.

### 3. Verify Completeness
```bash
../../scaffold/de doctor .
```
Expected: Exit code 0; confirms all dependencies and KB files present.

### 4. Check Build Status
```bash
../../scaffold/de status .
```
Expected: Summary of built components, instance ID, scope, mentors.

### 5. Detect Drift
```bash
../../scaffold/de diff .
```
Expected: Exit code 0; runtime matches built manifest.

---

## File Structure

```
acme-checkout-sre/
├── instance.yaml          # Identity, scope, settings, escalation config
├── skills.yaml            # Skill registry and dependencies
├── .env.example           # Environment variables (copy to .env for local testing)
├── README.md              # This file
├── Makefile               # Standard build targets
├── VERSION                # Semantic version (X.Y.Z)
├── kb/
│   └── team/
│       ├── _index.md                    # KB index and navigation
│       ├── service-overview.md          # Service architecture and team contacts
│       ├── cache-scaling-sop.md         # Scaling rules (R1, R2, R3)
│       └── checkout-oncall-runbook.md   # Incident response & escalation
└── runtime/               # Build output (gitignored)
    ├── CLAUDE.md          # Rendered system prompt
    ├── .claude/settings.json
    ├── kb/                # Compiled knowledge base
    ├── tests/             # Common guardrail tests
    └── .build-manifest.json
```

---

## Key Files

### instance.yaml
Defines the instance:
- **ID**: DE-ACME-CHECKOUT-001
- **Team**: acme-checkout-sre
- **Scope**: acme.storefront.checkout, acme.storefront.cart
- **Mentors**: mentor-one@acme.example, mentor-two@acme.example
- **Base**: Scaffold v0.1.0

See `/docs/10-scaffold/instance-yaml-spec.md` for full schema reference.

### skills.yaml
Declares skill dependencies:
- Registry: local (`file://../../skills/`)
- Dependencies: Currently empty (scalable for future ticket-review, metrics-fetch, etc.)

### kb/team/
Team-specific runbooks:
- **_index.md**: Navigation and role-based quick links
- **service-overview.md**: Service architecture, dependencies, team structure
- **cache-scaling-sop.md**: Scaling rules R1 (80% memory), R2 (2+ replicas), R3 (7-day cooldown)
- **checkout-oncall-runbook.md**: Incident response, escalation ladder, intelligent-staff constraints

---

## Workflow

### Adding a New Runbook
1. Create a new markdown file under `kb/team/`
2. Add a reference to `kb/team/_index.md`
3. Run `make build` to validate and compile
4. Commit the new file

### Updating Escalation Contacts
1. Edit `escalation.mentor_emails` in `instance.yaml`
2. Update mentor email in `kb/team/checkout-oncall-runbook.md`
3. Run `make build`
4. Commit and push

### Changing Service Scope
1. Update `scope.service_catalog` in `instance.yaml`
2. Run `../../scaffold/de validate .` to ensure no conflicts
3. If adding services outside acme-checkout-sre ownership, escalate to mentors first

---

## Make Targets

```bash
make help          # Show all targets
make build         # Validate, build, doctor, status
make rebuild       # Clean + build
make validate      # Schema validation only
make verify        # Validate + build (for CI)
make upgrade       # Check for base scaffold upgrades
make status        # Show build summary
make diff          # Detect runtime drift
make clean         # Erase runtime/
make start         # Launch Claude Code in runtime/
make serve         # Launch bridge (if enabled)
make doctor        # Environment checks
```

---

## Change Gateway Integration

All changes proposed by the intelligent-staff worker are logged at:
```
http://localhost:8801/changes
```

The Change Gateway:
- Accepts change proposals (POST /changes)
- Evaluates risk using mentor thresholds
- Routes to mentors for approval
- Logs events for audit and compliance

**Key Rule**: The intelligent-staff worker never executes changes directly. All proposals are reviewed and approved by mentors through the Change Gateway.

---

## Environment Setup

### Local Development

Copy `.env.example` to `.env` and update:

```bash
cp .env.example .env
# Edit .env with:
#  - CHANGE_GATEWAY_BASE=http://localhost:8801 (for local mock)
#  - DE_SCOPE_SERVICE_CATALOG=../../mocks/service_catalog.json
```

### Production

The Instance Manager injects production secrets as environment variables at deploy time. Do not commit real credentials to `.env` or git.

---

## CI/CD Pipeline

Standard instance CI (see `.github/workflows/instance-ci.yml`):

```
validate → build → doctor → kb_check → trigger_gate → smoke (common) → smoke (e2e) → release
```

All validation must pass before the instance can be deployed.

---

## Support & Escalation

- **Team Slack**: #acme-checkout-sre
- **Team Email**: acme-checkout-sre@acme.example
- **Mentors**: mentor-one@acme.example, mentor-two@acme.example
- **KB**: `kb/team/_index.md` (quick reference by role)

---

## Documentation

- **Instance YAML Spec**: `/docs/10-scaffold/instance-yaml-spec.md`
- **Creating Instances**: `/docs/20-instance/creating-an-instance.md`
- **KB Guide**: `/docs/20-instance/kb-guide.md`
- **Skills YAML Spec**: `/docs/20-instance/skills-yaml-spec.md`
- **Scaffold Design**: `/docs/10-scaffold/design.md`

---

## Maintenance

### Regular Tasks
- **Weekly**: Review cache metrics and scaling status
- **Post-Deployment**: Run `make diff` to ensure no drift
- **Quarterly**: Audit mentors list and escalation contacts
- **On Upgrade**: Run `make upgrade` to check for scaffold base updates

### Troubleshooting
- **Validation fails**: Check `instance.yaml` schema against `/docs/10-scaffold/instance-yaml-spec.md`
- **Build fails**: Run `../../scaffold/de doctor .` for detailed diagnostics
- **Drift detected**: Run `../../scaffold/de diff .` to identify changes
- **KB not loading**: Verify all paths in `kb/team/_index.md` exist and are readable

---

## License & Governance

This instance is governed by the Acme Checkout SRE team and the intelligent-staff worker Platform team. All changes must be reviewed via the Change Gateway before deployment.

---

**Instance ID**: DE-ACME-CHECKOUT-001  
**Team**: acme-checkout-sre  
**Version**: 0.1.0  
**Last Updated**: 2026-07-16
