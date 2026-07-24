"""Deterministic coverage for the access-review skill's core policy logic.

analyze_request.py is what actually decides PASS/FAIL — the role-catalog rule
(R1), the production time-boxing rule (R2), and the privileged-PII
manager-approval rule (R3) — and render_review.py turns that into the
human-facing review. Those scripts are pure stdlib; the agent only
orchestrates them. In CI without an ANTHROPIC_API_KEY the LLM-driven
triggers/safety/e2e gates are skipped, so this decision logic — the heart of
what this digital worker does — would otherwise be untested. These tests run
the scripts as subprocesses (like the agent does) against crafted requests.

Lives outside skills/skills/** on purpose, so it does not trip the skills-ci
version gate; it is collected by repo-ci's eval-tests job.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "skills" / "skills" / "access-review" / "scripts"


def run_analyze(request):
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "analyze_request.py"), "--request", "-"],
        input=json.dumps(request), capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def run_render(analysis, now="2026-01-01 00:00 UTC"):
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "render_review.py"), "--analysis", "-", "--now", now],
        input=json.dumps(analysis), capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def check(result, rule):
    return next(c for c in result["checks"] if c["rule"] == rule)


def request(**over):
    base = {
        "request_id": "AR-1", "requestor": "dev@acme.example",
        "service": "acme.storefront.checkout", "role": "admin",
        "environment": "production", "justification_ticket": "OPS-1",
        "duration_days": 30, "manager_approved": True,
    }
    base.update(over)
    return base


# ---- R1: role in catalog ---------------------------------------------------

def test_known_role_passes_catalog_check():
    r = run_analyze(request(role="viewer", environment="staging"))
    assert check(r, "requested_role_in_service_catalog")["status"] == "pass"


def test_unknown_role_fails_catalog_check():
    r = run_analyze(request(role="superuser"))
    assert check(r, "requested_role_in_service_catalog")["status"] == "fail"


def test_unknown_service_fails_catalog_check():
    r = run_analyze(request(service="acme.storefront.unknown"))
    assert check(r, "requested_role_in_service_catalog")["status"] == "fail"


# ---- R2: production time-boxing --------------------------------------------

def test_non_production_skips_time_box_rule():
    r = run_analyze(request(environment="staging", justification_ticket=None, duration_days=None))
    assert check(r, "production_grant_time_boxed")["status"] == "pass"


def test_production_without_ticket_or_duration_fails():
    r = run_analyze(request(justification_ticket=None, duration_days=None))
    c = check(r, "production_grant_time_boxed")
    assert c["status"] == "fail"
    assert "justification_ticket" in c["evidence"] and "standing" in c["evidence"]


def test_production_over_cap_fails():
    r = run_analyze(request(duration_days=120))
    c = check(r, "production_grant_time_boxed")
    assert c["status"] == "fail" and "exceeds" in c["evidence"]


def test_production_ticketed_and_time_boxed_passes():
    r = run_analyze(request(duration_days=90))  # exactly the cap
    assert check(r, "production_grant_time_boxed")["status"] == "pass"


# ---- R3: privileged PII needs manager approval -----------------------------

def test_privileged_pii_prod_without_manager_approval_fails():
    r = run_analyze(request(manager_approved=False))
    assert check(r, "privileged_pii_requires_manager_approval")["status"] == "fail"


def test_privileged_pii_prod_with_manager_approval_passes():
    r = run_analyze(request(manager_approved=True))
    assert check(r, "privileged_pii_requires_manager_approval")["status"] == "pass"


def test_viewer_on_pii_does_not_require_manager_approval():
    # viewer is not privileged -> rule not applicable even on a PII service.
    r = run_analyze(request(role="viewer", manager_approved=False))
    assert check(r, "privileged_pii_requires_manager_approval")["status"] == "pass"


def test_privileged_on_standard_service_does_not_require_manager_approval():
    r = run_analyze(request(service="acme.storefront.cart", role="operator", manager_approved=False))
    assert check(r, "privileged_pii_requires_manager_approval")["status"] == "pass"


# ---- summary + render ------------------------------------------------------

def test_summary_is_worst_status():
    clean = run_analyze(request())
    assert clean["summary"] == "pass"
    bad = run_analyze(request(manager_approved=False))
    assert bad["summary"] == "fail"


def test_render_is_comment_only_and_structured():
    out = run_render(run_analyze(request(manager_approved=False)))
    for heading in ("## Summary", "## Review Comment", "### Checks", "### Verified Inputs", "### Concerns"):
        assert heading in out
    assert "does **not** grant, revoke, or approve access" in out
    assert "No grant/revoke action was taken" in out
    # A failing check must surface under Concerns.
    assert "FAIL" in out and "manager_approved=true" in out
