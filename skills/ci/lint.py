#!/usr/bin/env python3
"""lint gate: static checks on a single skill directory.

Checks (skill-authoring-guide.md §1-2, release-and-ci.md §1 rule 2):
  1. SKILL.md exists with valid frontmatter: name, description, version
     (valid semver), risk_level in {L1, L2, L3}, allowed-tools (a list).
  2. No bare `Bash` entry in allowed-tools — must be prefix-scoped, e.g.
     `Bash(uv:*)`. This is a hard capability-boundary rule.
  3. Required test files exist: tests/triggers.yaml, tests/safety.yaml,
     tests/test-cases.md, and at least one tests/*.mock.yaml.
  4. Every scenario in test-cases.md's coverage table maps to an existing
     test case in triggers.yaml / safety.yaml / *.mock.yaml.

Usage:
    uv run --project skills/ci python skills/ci/lint.py <skill-dir>

Exit 0 if clean, 1 if any violation (each violation is printed).

Adaptation note (spec §4 of the coverage-mapping rule): test-cases.md's
table has columns `Type | Label | Required | Reason`, not a literal
"test-id" column. Test cases carry a `case_id` of shape
`<skill>.<type>.<label>.<hash>` (the hash isn't listed in the table), so
this script matches each table row to test cases by `(type, label)` pair
extracted from every `evaluation:` block, rather than by exact case_id
string.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import is_valid_semver, read_frontmatter, FrontmatterError  # noqa: E402

RISK_LEVELS = {"L1", "L2", "L3"}
BARE_BASH_RULE = "no-bare-bash"


def check_frontmatter(skill_dir: Path, violations: list[str]) -> dict:
    skill_md = skill_dir / "SKILL.md"
    try:
        fm = read_frontmatter(skill_md)
    except FrontmatterError as exc:
        violations.append(f"frontmatter: {exc}")
        return {}

    for field in ("name", "description", "version", "risk_level", "allowed-tools"):
        if field not in fm:
            violations.append(f"frontmatter: missing required field '{field}'")

    version = fm.get("version")
    if version is not None and not is_valid_semver(version):
        violations.append(
            f"frontmatter: version {version!r} is not strict semver (MAJOR.MINOR.PATCH)"
        )

    risk_level = fm.get("risk_level")
    if risk_level is not None and risk_level not in RISK_LEVELS:
        violations.append(
            f"frontmatter: risk_level {risk_level!r} not one of {sorted(RISK_LEVELS)}"
        )

    allowed_tools = fm.get("allowed-tools")
    if allowed_tools is not None:
        if not isinstance(allowed_tools, list):
            violations.append("frontmatter: allowed-tools must be a list")
        else:
            for entry in allowed_tools:
                if entry == "Bash":
                    violations.append(
                        f"allowed-tools: bare 'Bash' entry is forbidden [{BARE_BASH_RULE}] "
                        "— must be prefix-scoped, e.g. \"Bash(uv:*)\""
                    )
                elif isinstance(entry, str) and entry.startswith("Bash") and not re.match(
                    r"^Bash\([^)]+:\*\)$", entry
                ):
                    violations.append(
                        f"allowed-tools: entry {entry!r} is not a valid prefix-scoped "
                        f"Bash form [{BARE_BASH_RULE}] — expected \"Bash(<prefix>:*)\""
                    )

    return fm


def check_required_test_files(skill_dir: Path, violations: list[str]) -> None:
    tests_dir = skill_dir / "tests"
    required = ["triggers.yaml", "safety.yaml", "test-cases.md"]
    for name in required:
        if not (tests_dir / name).is_file():
            violations.append(f"tests: required file missing: tests/{name}")

    mock_files = sorted(tests_dir.glob("*.mock.yaml")) if tests_dir.is_dir() else []
    if not mock_files:
        violations.append("tests: no tests/*.mock.yaml e2e fixture found (need at least one)")


def collect_case_type_labels(data) -> set[tuple[str, str]]:
    """Recursively walk a parsed YAML structure and collect every
    (type, label) pair found under an `evaluation:` block."""
    found: set[tuple[str, str]] = set()

    def walk(node):
        if isinstance(node, dict):
            ev = node.get("evaluation")
            if isinstance(ev, dict) and "type" in ev and "label" in ev:
                found.add((str(ev["type"]), str(ev["label"])))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def parse_coverage_table(test_cases_md: Path) -> list[tuple[str, str]]:
    """Parse the `| Type | Label | Required | Reason |` markdown table.

    Returns a list of (type, label) rows. If the table header doesn't match
    exactly, falls back to a best-effort parse of any pipe-table found,
    assuming the first two columns are type and label.
    """
    text = test_cases_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    rows: list[tuple[str, str]] = []

    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and "type" in stripped.lower() and "label" in stripped.lower():
            header_idx = i
            break

    if header_idx is None:
        return rows

    # Skip the header row and the '---' separator row.
    i = header_idx + 2
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[0].lower() != "type":
            rows.append((cells[0], cells[1]))
        i += 1

    return rows


def check_coverage(skill_dir: Path, violations: list[str]) -> None:
    tests_dir = skill_dir / "tests"
    test_cases_md = tests_dir / "test-cases.md"
    if not test_cases_md.is_file():
        return  # already flagged as a missing required file

    table_rows = parse_coverage_table(test_cases_md)

    yaml_files = list(tests_dir.glob("*.yaml"))
    known_pairs: set[tuple[str, str]] = set()
    for yf in yaml_files:
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            violations.append(f"tests/{yf.name}: invalid YAML: {exc}")
            continue
        known_pairs |= collect_case_type_labels(data)

    for row_type, row_label in table_rows:
        if (row_type, row_label) not in known_pairs:
            violations.append(
                f"tests/test-cases.md: coverage row '{row_type}.{row_label}' has no "
                "matching evaluation case_id in tests/*.yaml or tests/*.mock.yaml"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path, help="path to a skills/<name>/ directory")
    args = parser.parse_args()

    skill_dir: Path = args.skill_dir
    violations: list[str] = []

    if not skill_dir.is_dir():
        print(f"lint: {skill_dir} is not a directory")
        return 1

    check_frontmatter(skill_dir, violations)
    check_required_test_files(skill_dir, violations)
    check_coverage(skill_dir, violations)

    if violations:
        for v in violations:
            print(f"lint fail: {v}")
        return 1

    print(f"lint ok: {skill_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
