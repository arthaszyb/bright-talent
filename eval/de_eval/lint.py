"""`de-eval lint` — static checks, no agent execution (eval-spec.md §2).

Checks run in order and *accumulate* errors (report everything found), but
the CLI treats "first failing rule" as the headline per the spec's exit
contract: exit 0 clean, exit 1 with every violation printed to stderr.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from de_eval import coverage
from de_eval.frontmatter import FrontmatterError, parse_frontmatter

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
RISK_LEVELS = {"L1", "L2", "L3"}
REQUIRED_FRONTMATTER_KEYS = ("name", "description", "version", "allowed-tools")
REQUIRED_TEST_FILES = ("tests/triggers.yaml", "tests/safety.yaml", "tests/test-cases.md")


@dataclass
class LintResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def _check_bare_bash(allowed_tools, errors: list[str]) -> None:
    if not isinstance(allowed_tools, list):
        errors.append("allowed-tools: must be a list")
        return
    for entry in allowed_tools:
        if entry == "Bash":
            errors.append(
                "allowed-tools: bare 'Bash' is forbidden — use a command-prefix "
                "whitelist, e.g. 'Bash(uv:*)'"
            )


def _check_dependencies(frontmatter: dict, errors: list[str]) -> None:
    meta = frontmatter.get("metadata") or {}
    de_platform = meta.get("de_platform") or {}
    deps = de_platform.get("dependencies")
    if deps is None:
        return
    if not isinstance(deps, list):
        errors.append("metadata.de_platform.dependencies: must be a list")
        return
    if "uvx" in deps:
        errors.append(
            "metadata.de_platform.dependencies: 'uvx' must not be declared "
            "(implicitly available)"
        )


def _check_changelog(skill_dir: Path, version: str, errors: list[str]) -> None:
    changelog = skill_dir / "CHANGELOG.md"
    if not changelog.is_file():
        errors.append("CHANGELOG.md: required file missing")
        return
    text = changelog.read_text(encoding="utf-8")
    # Accept "## 0.1.0", "## v0.1.0", or "## skill/v0.1.0" style headings.
    pattern = re.compile(
        rf"^#{{1,3}}\s*\S*v?{re.escape(version)}\b", re.MULTILINE
    )
    if not pattern.search(text):
        errors.append(f"CHANGELOG.md: no entry found for current version '{version}'")


def lint_skill(skill_dir: Path) -> LintResult:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"

    try:
        frontmatter = parse_frontmatter(skill_md)
    except FrontmatterError as e:
        return LintResult(ok=False, errors=[str(e)])

    # 1. Required frontmatter keys.
    missing = [k for k in REQUIRED_FRONTMATTER_KEYS if k not in frontmatter]
    if missing:
        errors.append(f"SKILL.md frontmatter: missing required keys: {missing}")
    if "risk_level" not in frontmatter:
        errors.append("SKILL.md frontmatter: missing required key: risk_level")
    elif frontmatter["risk_level"] not in RISK_LEVELS:
        errors.append(
            f"SKILL.md frontmatter: risk_level must be one of {sorted(RISK_LEVELS)}, "
            f"got {frontmatter['risk_level']!r}"
        )

    # 2. version is valid semver.
    version = frontmatter.get("version")
    if version is not None and not SEMVER_RE.match(str(version)):
        errors.append(f"SKILL.md frontmatter: version '{version}' is not strict semver X.Y.Z")

    # 3. No bare Bash in allowed-tools.
    if "allowed-tools" in frontmatter:
        _check_bare_bash(frontmatter["allowed-tools"], errors)

    # 4. Declared dependencies resolve (uvx must not be declared).
    _check_dependencies(frontmatter, errors)

    # 5. Required files present.
    for rel in REQUIRED_TEST_FILES:
        if not (skill_dir / rel).is_file():
            errors.append(f"{rel}: required file missing")
    if not list(skill_dir.glob("tests/*.mock.yaml")):
        errors.append("tests/*.mock.yaml: at least one command-replay mock file is required")
    if version is not None and SEMVER_RE.match(str(version)):
        _check_changelog(skill_dir, str(version), errors)

    # 6. Coverage table consistency.
    if (skill_dir / "tests" / "test-cases.md").is_file():
        errors.extend(coverage.check_coverage(skill_dir))

    return LintResult(ok=not errors, errors=errors)


def lint_instance_coverage(instance_dir: Path) -> LintResult:
    """Instance-level `coverage-review` variant: lint tests/test-cases.md only."""
    errors: list[str] = []
    md_path = instance_dir / "tests" / "test-cases.md"
    if not md_path.is_file():
        return LintResult(ok=False, errors=[f"{md_path}: required file missing (run ./de build first)"])
    errors.extend(coverage.check_coverage(instance_dir))
    return LintResult(ok=not errors, errors=errors)
