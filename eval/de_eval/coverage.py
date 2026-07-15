"""tests/test-cases.md coverage-table parsing + cross-checking.

eval-spec.md §2.6: every `type.label` referenced by an `evaluation.case_id`
in triggers.yaml / safety.yaml / *.mock.yaml must have a row in the
Evaluation Coverage table, and every `Required: yes` row must be backed by
at least one referencing case.
"""

from __future__ import annotations

import re
from pathlib import Path

from de_eval.yaml_io import load_yaml


def parse_coverage_table(md_path: Path) -> list[dict[str, str]]:
    """Returns rows: [{"type":..., "label":..., "required":..., "reason":...}]."""
    if not md_path.is_file():
        return []
    text = md_path.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    header_seen = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not header_seen:
            lowered = [c.lower() for c in cells]
            if lowered[:4] == ["type", "label", "required", "reason"]:
                header_seen = True
            continue
        # separator row: |---|---|---|---|
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) < 4:
            continue
        rows.append(
            {
                "type": cells[0],
                "label": cells[1],
                "required": cells[2].lower(),
                "reason": cells[3],
            }
        )
    return rows


def _cases_from_eval_block(block: dict | None) -> tuple[str, str] | None:
    if not isinstance(block, dict):
        return None
    t, label = block.get("type"), block.get("label")
    if t and label:
        return (str(t), str(label))
    return None


def collect_referenced_type_labels(skill_dir: Path) -> set[tuple[str, str]]:
    """Scans triggers.yaml, safety.yaml, and *.mock.yaml for evaluation.type/.label."""
    tests_dir = skill_dir / "tests"
    referenced: set[tuple[str, str]] = set()

    triggers_path = tests_dir / "triggers.yaml"
    if triggers_path.is_file():
        data = load_yaml(triggers_path) or {}
        for key in ("should_trigger", "should_not_trigger", "cases"):
            for case in data.get(key) or []:
                tl = _cases_from_eval_block(case.get("evaluation"))
                if tl:
                    referenced.add(tl)

    safety_path = tests_dir / "safety.yaml"
    if safety_path.is_file():
        data = load_yaml(safety_path) or {}
        for key in ("must_be_denied", "must_refuse"):
            for case in data.get(key) or []:
                tl = _cases_from_eval_block(case.get("evaluation"))
                if tl:
                    referenced.add(tl)

    for mock_path in sorted(tests_dir.glob("*.mock.yaml")):
        data = load_yaml(mock_path) or {}
        tl = _cases_from_eval_block(data.get("evaluation"))
        if tl:
            referenced.add(tl)

    return referenced


def check_coverage(skill_dir: Path) -> list[str]:
    """Returns a list of coverage-consistency violations (empty = clean)."""
    errors: list[str] = []
    md_path = skill_dir / "tests" / "test-cases.md"
    rows = parse_coverage_table(md_path)
    if not rows:
        errors.append(f"{md_path}: no Evaluation Coverage table found (Type|Label|Required|Reason)")
        return errors

    row_keys = {(r["type"], r["label"]) for r in rows}
    referenced = collect_referenced_type_labels(skill_dir)

    for t, label in sorted(referenced):
        if (t, label) not in row_keys:
            errors.append(
                f"tests/test-cases.md: missing coverage row for referenced case '{t}.{label}'"
            )

    for r in rows:
        if r["required"] == "yes" and (r["type"], r["label"]) not in referenced:
            errors.append(
                f"tests/test-cases.md: row '{r['type']}.{r['label']}' is Required: yes but no "
                "test case references it"
            )

    return errors
