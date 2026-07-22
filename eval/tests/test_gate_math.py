"""Release-gate threshold arithmetic (triggers / safety pass ratios).

These two reports decide whether a skill passes the triggers and safety
gates on the release pipeline. The scoring is pure and worth pinning — a
regression here would silently pass or fail releases. In particular the
safety gate must stay strictly stricter than the triggers gate.
"""
from __future__ import annotations

from de_eval import safety, triggers
from de_eval.safety import SafetyCaseResult, SafetyReport
from de_eval.triggers import CaseResult, TriggersReport


def trig(passed):
    return CaseResult(case_id="c", prompt="p", expected="should_trigger", triggered=passed, passed=passed)


def saf(passed):
    return SafetyReport(results=[
        SafetyCaseResult(name="n", case_id="c", prompt="p", expected_verdict="deny", passed=passed, reason="")
    ])


# ---- default thresholds (the load-bearing invariant) -----------------------

def test_default_thresholds_match_spec():
    assert triggers.DEFAULT_PASS_THRESHOLD == 0.9
    assert safety.DEFAULT_PASS_THRESHOLD == 1.0


def test_safety_gate_is_stricter_than_triggers_gate():
    # A single guardrail failure must fail safety but may be tolerated by triggers.
    assert safety.DEFAULT_PASS_THRESHOLD > triggers.DEFAULT_PASS_THRESHOLD


# ---- ratio / ok arithmetic -------------------------------------------------

def test_empty_report_ratio_is_one_and_ok():
    assert TriggersReport().ratio == 1.0
    assert TriggersReport().ok is True
    assert SafetyReport().ratio == 1.0
    assert SafetyReport().ok is True


def test_triggers_ratio_and_threshold_boundary():
    r = TriggersReport(results=[trig(True) for _ in range(9)] + [trig(False)])
    assert r.ratio == 0.9
    assert r.ok is True  # 0.9 >= 0.9 threshold
    r2 = TriggersReport(results=[trig(True) for _ in range(8)] + [trig(False), trig(False)])
    assert r2.ratio == 0.8
    assert r2.ok is False


def test_safety_one_failure_fails_the_gate():
    r = SafetyReport(results=[
        SafetyCaseResult("n", "c", "p", "deny", passed=True, reason=""),
        SafetyCaseResult("n", "c2", "p", "deny", passed=False, reason="leaked"),
    ])
    assert r.ratio == 0.5
    assert r.ok is False


def test_safety_all_pass_is_ok():
    assert saf(True).ok is True


def test_yaml_declared_threshold_overrides_default():
    # A report constructed with a custom threshold honors it.
    r = TriggersReport(results=[trig(True), trig(False)], pass_threshold=0.5)
    assert r.ratio == 0.5 and r.ok is True
