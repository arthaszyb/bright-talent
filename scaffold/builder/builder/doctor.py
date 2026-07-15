"""Environment + config completeness checks.

Spec: docs/10-scaffold/design.md §2 / de-cli-spec.md §2.5.
Reports each check pass/fail; any failure -> exit 1.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

REQUIRED_RUNTIME_FILES = (
    "CLAUDE.md",
    ".claude/settings.json",
    ".mcp.json",
    ".claude/policy/security.yaml",
    ".claude/policy/sensitive-data.yaml",
    ".claude/policy/operation-levels.yaml",
    ".claude/policy/change-freeze.yaml",
)

HOOK_FILES = (
    ".claude/hooks/context-isolator.py",
    ".claude/hooks/escalation-guard.py",
    ".claude/hooks/injection-detector.sh",
    ".claude/hooks/input-sanitizer.sh",
    ".claude/hooks/result-sanitizer.sh",
    ".claude/hooks/skill-gate.py",
)


def run_checks(instance_dir: Path) -> list[tuple[str, bool, str]]:
    """Returns [(check_name, passed, detail), ...]."""
    checks: list[tuple[str, bool, str]] = []
    runtime_dir = instance_dir / "runtime"

    checks.append(("runtime/ exists", runtime_dir.is_dir(), str(runtime_dir)))

    for rel in REQUIRED_RUNTIME_FILES:
        p = runtime_dir / rel
        checks.append((f"required file: {rel}", p.is_file(), str(p)))

    for rel in HOOK_FILES:
        p = runtime_dir / rel
        exists = p.is_file()
        executable = exists and os.access(p, os.X_OK)
        checks.append((f"hook executable: {rel}", exists and executable, str(p)))

    for artifact in (".build-manifest.json", ".build-info.json", ".managed-files.json"):
        p = instance_dir / artifact
        checks.append((f"build artifact present: {artifact}", p.is_file(), str(p)))

    policy_dir = runtime_dir / ".claude" / "policy"
    for policy_file in ("security.yaml", "sensitive-data.yaml", "operation-levels.yaml", "change-freeze.yaml"):
        p = policy_dir / policy_file
        ok = False
        detail = str(p)
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                ok = isinstance(data, dict) and "rules" in data
            except yaml.YAMLError as e:
                detail = f"parse error: {e}"
        checks.append((f"policy parses: {policy_file}", ok, detail))

    tests_dir = runtime_dir / "tests"
    seed_count = len(list(tests_dir.glob("*.mock.yaml"))) if tests_dir.is_dir() else 0
    checks.append(("seeded tests present (5 common guardrail cases)", seed_count == 5, f"{seed_count} found"))

    return checks


def main(instance_dir: Path, extra: list[str]) -> int:
    checks = run_checks(instance_dir)
    all_ok = True
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok:
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
