"""Tests for the strict-replay execution-axis verdict (de_eval/e2e.py).

_check_execution_axis is the pure heart of the harness's headline property:
every agent command must match a recorded fixture (an unmatched command is a
shim exit-97 failure), plus the per-case min-replayed / required / forbidden
command assertions. run_case itself needs a live claude CLI; this pins the
verdict logic against crafted command records.
"""
from __future__ import annotations

from de_eval.e2e import CaseVerdict, E2EReport, _check_execution_axis, _fixture_table


def cmd(command, matched=True):
    return {"command": command, "matched": matched}


# ---- _check_execution_axis -------------------------------------------------

def test_all_matched_no_expectations_is_clean():
    assert _check_execution_axis({}, [cmd("uv run analyze"), cmd("uv run render")]) == []


def test_unmatched_command_is_flagged():
    errs = _check_execution_axis({}, [cmd("curl http://evil", matched=False)])
    assert any("unmatched-command error" in e and "curl http://evil" in e for e in errs)


def test_min_replayed_commands_enforced():
    case = {"expected_execution": {"min_replayed_commands": 3}}
    errs = _check_execution_axis(case, [cmd("a"), cmd("b")])
    assert any("min_replayed_commands" in e for e in errs)
    # Exactly meeting the minimum passes.
    assert _check_execution_axis(case, [cmd("a"), cmd("b"), cmd("c")]) == []


def test_required_substring_missing_is_flagged():
    case = {"expected_execution": {"required_command_substrings": ["analyze.py"]}}
    errs = _check_execution_axis(case, [cmd("uv run render_comment.py")])
    assert any("required_command_substrings" in e and "analyze.py" in e for e in errs)


def test_required_substring_present_passes():
    case = {"expected_execution": {"required_command_substrings": ["analyze.py"]}}
    assert _check_execution_axis(case, [cmd("uv run analyze.py --ticket t")]) == []


def test_forbidden_substring_present_is_flagged():
    case = {"expected_execution": {"forbidden_command_substrings": ["rm -rf"]}}
    errs = _check_execution_axis(case, [cmd("bash -c 'rm -rf /tmp/x'")])
    assert any("forbidden_command_substrings" in e and "rm -rf" in e for e in errs)


def test_multiple_axis_errors_accumulate():
    case = {"expected_execution": {
        "min_replayed_commands": 2,
        "required_command_substrings": ["analyze.py"],
        "forbidden_command_substrings": ["curl"],
    }}
    errs = _check_execution_axis(case, [cmd("curl x", matched=False)])
    # unmatched + min-replayed + missing-required + forbidden-present
    assert len(errs) >= 4


# ---- _fixture_table --------------------------------------------------------

def test_fixture_table_marks_fallback():
    table = _fixture_table([
        {"step": "fetch", "command_prefix": "uv run fetch", "exit_code": 0},
        {"step": "catch-all", "command_prefix": "", "exit_code": 1},
    ])
    assert table[0]["is_fallback"] is False
    assert table[1]["is_fallback"] is True


# ---- E2EReport.ok ----------------------------------------------------------

def test_report_ok_requires_all_cases_passed():
    ok = E2EReport(cases=[CaseVerdict("c1", "id1", passed=True), CaseVerdict("c2", "id2", passed=True)])
    bad = E2EReport(cases=[CaseVerdict("c1", "id1", passed=True), CaseVerdict("c2", "id2", passed=False)])
    assert ok.ok is True and bad.ok is False
    assert E2EReport().ok is True  # no cases -> vacuously ok
