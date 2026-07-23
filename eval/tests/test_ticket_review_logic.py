"""Deterministic coverage for the ticket-review skill's core SOP logic.

analyze.py is what actually decides PASS/FAIL — the memory-utilization
prediction (R1), the minimum-replica rule (R2), and the campaign-cooldown
rule (R3) — and render_comment.py turns that into the human-facing review.
Those scripts are pure stdlib; the agent only orchestrates them. Yet in CI
without an ANTHROPIC_API_KEY the LLM-driven triggers/safety/e2e gates are
skipped, so this decision logic — the heart of what the digital employee
does — was otherwise untested here. These tests run the scripts as
subprocesses (like the agent does) against crafted fixtures.

Lives outside skills/skills/** on purpose, so it does not trip the skills-ci
version gate; it is collected by repo-ci's eval-tests job.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "skills" / "skills" / "ticket-review" / "scripts"


def run_analyze(tmp_path, ticket, metrics):
    (tmp_path / "t.json").write_text(json.dumps(ticket))
    (tmp_path / "m.json").write_text(json.dumps(metrics))
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "analyze.py"),
         "--ticket", str(tmp_path / "t.json"), "--metrics", str(tmp_path / "m.json")],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def check(result, rule):
    return next(c for c in result["checks"] if c["rule"] == rule)


def ticket(**over):
    base = {
        "ticket_id": "T", "cluster": "acme.storefront.checkout.cart",
        "change_type": "scale_up",
        "current": {"nodes": 6, "mem_per_node_gb": 8, "replicas": 3},
        "target": {"nodes": 9, "mem_per_node_gb": 8, "replicas": 3},
        "recent_campaign_window": None,
    }
    base.update(over)
    return base


# ---- R1: predicted utilization ---------------------------------------------

def test_r1_pass_when_predicted_under_70(tmp_path):
    # 48GB @ 82% = 39.36 used; over 72GB target -> 54.7% -> pass
    r = run_analyze(tmp_path, ticket(), {"mem_util_peak_pct": 82})
    assert check(r, "predicted_peak_memory_utilization_below_80pct")["status"] == "pass"
    assert r["predicted_mem_util_pct"] == 54.7


def test_r1_warn_between_70_and_80(tmp_path):
    # used 36 over target 48 -> 75% -> warn (>= 70, < 80)
    t = ticket(current={"nodes": 6, "mem_per_node_gb": 8, "replicas": 3},
               target={"nodes": 6, "mem_per_node_gb": 8, "replicas": 3})
    r = run_analyze(tmp_path, t, {"mem_util_peak_pct": 75})
    assert check(r, "predicted_peak_memory_utilization_below_80pct")["status"] == "warn"


def test_r1_fail_at_or_over_80(tmp_path):
    # scale-down 48GB @ 90% = 43.2 used over 32GB target -> 135% -> fail
    t = ticket(change_type="scale_down",
               current={"nodes": 6, "mem_per_node_gb": 8, "replicas": 3},
               target={"nodes": 4, "mem_per_node_gb": 8, "replicas": 3})
    r = run_analyze(tmp_path, t, {"mem_util_peak_pct": 90})
    assert check(r, "predicted_peak_memory_utilization_below_80pct")["status"] == "fail"
    assert r["summary"] == "fail"


# ---- R2: minimum replicas --------------------------------------------------

def test_r2_fail_below_two_replicas(tmp_path):
    t = ticket(change_type="scale_down", target={"nodes": 4, "mem_per_node_gb": 8, "replicas": 1})
    r = run_analyze(tmp_path, t, {"mem_util_peak_pct": 35})
    assert check(r, "minimum_replica_count")["status"] == "fail"


def test_r2_pass_at_two(tmp_path):
    t = ticket(target={"nodes": 9, "mem_per_node_gb": 8, "replicas": 2})
    r = run_analyze(tmp_path, t, {"mem_util_peak_pct": 40})
    assert check(r, "minimum_replica_count")["status"] == "pass"


# ---- R3: campaign cooldown -------------------------------------------------

def test_r3_fail_scale_down_within_cooldown(tmp_path):
    t = ticket(change_type="scale_down",
               target={"nodes": 4, "mem_per_node_gb": 8, "replicas": 3},
               recent_campaign_window={"name": "flash-sale", "ends_days_ago": 2})
    r = run_analyze(tmp_path, t, {"mem_util_peak_pct": 30})
    c = check(r, "campaign_cooldown_for_scale_down")
    assert c["status"] == "fail" and "flash-sale" in c["evidence"]


def test_r3_pass_scale_down_after_cooldown(tmp_path):
    t = ticket(change_type="scale_down",
               target={"nodes": 4, "mem_per_node_gb": 8, "replicas": 3},
               recent_campaign_window={"name": "flash-sale", "ends_days_ago": 30})
    r = run_analyze(tmp_path, t, {"mem_util_peak_pct": 30})
    assert check(r, "campaign_cooldown_for_scale_down")["status"] == "pass"


def test_r3_not_applicable_for_scale_up(tmp_path):
    r = run_analyze(tmp_path, ticket(change_type="scale_up"), {"mem_util_peak_pct": 40})
    c = check(r, "campaign_cooldown_for_scale_down")
    assert c["status"] == "pass" and "not applicable" in c["evidence"]


# ---- summary precedence + render -------------------------------------------

def test_summary_is_worst_status(tmp_path):
    # R1 pass, R2 fail, R3 fail -> overall fail
    t = ticket(change_type="scale_down",
               target={"nodes": 4, "mem_per_node_gb": 8, "replicas": 1},
               recent_campaign_window={"name": "c", "ends_days_ago": 1})
    r = run_analyze(tmp_path, t, {"mem_util_peak_pct": 35})
    assert r["summary"] == "fail"


def test_render_comment_reflects_fail_and_stays_advisory(tmp_path):
    t = ticket(ticket_id="1002", change_type="scale_down",
               target={"nodes": 4, "mem_per_node_gb": 8, "replicas": 1},
               recent_campaign_window={"name": "mid-year-flash-sale", "ends_days_ago": 2})
    analysis = run_analyze(tmp_path, t, {"mem_util_peak_pct": 35})
    (tmp_path / "a.json").write_text(json.dumps(analysis))
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "render_comment.py"), "--analysis", str(tmp_path / "a.json")],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    md = proc.stdout
    assert "FAIL" in md
    assert "minimum_replica_count" in md and "campaign_cooldown_for_scale_down" in md
    # Propose-don't-execute: the review must never approve or reject.
    assert "does **not** approve or reject" in md
    assert "approve" not in md.lower().split("does **not**")[0]
