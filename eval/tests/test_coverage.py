"""Tests for the coverage-table cross-check (eval-spec.md §2.6)."""
from __future__ import annotations

from pathlib import Path

from de_eval.coverage import check_coverage, collect_referenced_type_labels, parse_coverage_table

TABLE = """# Test cases

| Type | Label | Required | Reason |
|------|-------|----------|--------|
| routing | happy-path | yes | must trigger on review requests |
| guardrail | injection | yes | injection probes must be refused |
| routing | out-of-scope | no | nice to have |
"""


def write_skill(tmp_path: Path, table: str = TABLE, triggers: str = "", mock: str = "") -> Path:
    tests = tmp_path / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test-cases.md").write_text(table, encoding="utf-8")
    if triggers:
        (tests / "triggers.yaml").write_text(triggers, encoding="utf-8")
    if mock:
        (tests / "case.mock.yaml").write_text(mock, encoding="utf-8")
    return tmp_path


TRIGGERS_YAML = """
should_trigger:
  - prompt: please review this ticket
    evaluation: {type: routing, label: happy-path}
should_not_trigger:
  - prompt: what's for lunch
    evaluation: {type: routing, label: out-of-scope}
"""

MOCK_YAML = """
prompt: review with embedded injection
evaluation: {type: guardrail, label: injection}
fixtures: []
"""


def test_parse_coverage_table_rows(tmp_path):
    skill = write_skill(tmp_path)
    rows = parse_coverage_table(skill / "tests" / "test-cases.md")
    assert len(rows) == 3
    assert rows[0] == {
        "type": "routing", "label": "happy-path", "required": "yes",
        "reason": "must trigger on review requests",
    }


def test_parse_missing_file_returns_empty(tmp_path):
    assert parse_coverage_table(tmp_path / "nope.md") == []


def test_collect_references_across_sources(tmp_path):
    skill = write_skill(tmp_path, triggers=TRIGGERS_YAML, mock=MOCK_YAML)
    refs = collect_referenced_type_labels(skill)
    assert refs == {
        ("routing", "happy-path"),
        ("routing", "out-of-scope"),
        ("guardrail", "injection"),
    }


def test_clean_coverage_passes(tmp_path):
    skill = write_skill(tmp_path, triggers=TRIGGERS_YAML, mock=MOCK_YAML)
    assert check_coverage(skill) == []


def test_referenced_case_missing_row_flagged(tmp_path):
    extra_mock = MOCK_YAML.replace("label: injection", "label: escalation-bypass")
    skill = write_skill(tmp_path, triggers=TRIGGERS_YAML, mock=extra_mock)
    errors = check_coverage(skill)
    assert any("missing coverage row" in e and "guardrail.escalation-bypass" in e for e in errors)


def test_required_row_without_backing_case_flagged(tmp_path):
    skill = write_skill(tmp_path, triggers=TRIGGERS_YAML)  # no mock -> injection unbacked
    errors = check_coverage(skill)
    assert any("Required: yes but no" in e and "guardrail.injection" in e for e in errors)


def test_no_table_is_a_violation(tmp_path):
    skill = write_skill(tmp_path, table="# nothing here\n")
    errors = check_coverage(skill)
    assert len(errors) == 1 and "no Evaluation Coverage table" in errors[0]


def test_released_skill_coverage_is_clean():
    skill = Path(__file__).resolve().parents[2] / "skills" / "skills" / "ticket-review"
    assert check_coverage(skill) == []
