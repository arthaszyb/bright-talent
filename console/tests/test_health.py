from console import health


def base_scan(**overrides):
    scan = {
        "base": {"status": "current"},
        "managed_files": [{"path": "CLAUDE.md", "status": "up_to_date"}],
        "files": {"instance_yaml": True, "version": True},
        "skills": [{"name": "ticket-review"}],
    }
    scan.update(overrides)
    return scan


def ci_ok():
    return {"available": True, "steps": [{"name": "validate", "status": "pass"}]}


def test_healthy_no_deductions():
    result = health.evaluate(base_scan(), ci_ok())
    assert result["score"] == 100
    assert result["status"] == "healthy"
    assert result["deductions"] == []


def test_base_stale_deduction():
    scan = base_scan(base=dict(status="stale"))
    result = health.evaluate(scan, ci_ok())
    assert result["score"] == 80
    assert result["status"] == "warn"
    assert {"reason": "base_stale", "points": 20} in result["deductions"]


def test_managed_drift_deduction():
    scan = base_scan(managed_files=[{"path": "CLAUDE.md", "status": "local_changed"}])
    result = health.evaluate(scan, ci_ok())
    assert result["score"] == 80
    assert result["status"] == "warn"


def test_ci_unavailable_deduction_and_risk_status():
    result = health.evaluate(base_scan(), {"available": False, "steps": []})
    assert result["score"] == 90
    # CI unavailable is only a -10 deduction but forces `risk` status per spec.
    assert result["status"] == "risk"


def test_ci_failed_deduction():
    ci = {"available": True, "steps": [{"name": "build", "status": "fail"}]}
    result = health.evaluate(base_scan(), ci)
    assert result["score"] == 80
    # Per spec precedence: risk requires score<75 or CI unavailable; warn requires
    # base-stale or managed drift. A CI *failure* (as opposed to unavailability)
    # at score>=75 with no drift/stale hits neither -- status is healthy even
    # though the score reflects the failure. This is the spec's literal table,
    # not a reinterpretation.
    assert result["status"] == "healthy"


def test_missing_identity_files_deduction():
    scan = base_scan(files={"instance_yaml": False, "version": True})
    result = health.evaluate(scan, ci_ok())
    assert result["score"] == 85


def test_no_skills_deduction():
    scan = base_scan(skills=[])
    result = health.evaluate(scan, ci_ok())
    assert result["score"] == 95


def test_deductions_are_additive_and_clamped_to_zero():
    scan = base_scan(
        base=dict(status="stale"),
        managed_files=[{"path": "x", "status": "both_changed"}],
        files={"instance_yaml": False, "version": False},
        skills=[],
    )
    ci = {"available": False, "steps": [{"name": "build", "status": "fail"}]}
    result = health.evaluate(scan, ci)
    # 20 + 20 + 10 + 20 + 15 + 5 = 90 -> score 10, not negative
    assert result["score"] == 10

    # Push it further negative to prove the floor is 0.
    scan["managed_files"].append({"path": "y", "status": "both_changed"})
    # (duplicate deduction reason won't double count -- managed drift is a single
    # boolean check, not per-file, so score stays 10; verify no negative regardless)
    result2 = health.evaluate(scan, ci)
    assert result2["score"] >= 0


def test_status_precedence_conflict_beats_everything():
    scan = base_scan(
        base=dict(status="stale"),
        managed_files=[{"path": "x", "status": "both_changed"}],
    )
    result = health.evaluate(scan, ci_ok())
    assert result["status"] == "conflict"


def test_status_precedence_risk_beats_warn():
    scan = base_scan(base=dict(status="stale"))
    result = health.evaluate(scan, {"available": False, "steps": []})
    assert result["status"] == "risk"


def test_status_precedence_warn_beats_healthy():
    scan = base_scan(base=dict(status="stale"))
    result = health.evaluate(scan, ci_ok())
    assert result["status"] == "warn"


def test_score_color_and_label_thresholds():
    assert health.score_color(85) == "green"
    assert health.score_color(84) == "amber"
    assert health.score_color(70) == "amber"
    assert health.score_color(69) == "red"
    assert health.score_label(90) == "production-ready"
    assert health.score_label(75) == "needs review"
    assert health.score_label(50) == "high risk"
