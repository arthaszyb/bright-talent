"""Shared helpers for the skills registry CI gate scripts.

Every gate (`detect_release.py`, `lint.py`, `version_check.py`) is a plain
script, callable locally via `uv run` and from `.github/workflows/skills-ci.yml`
(DESIGN.md S4). This module holds the bits they all need: reading SKILL.md
frontmatter and validating strict semver.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class FrontmatterError(ValueError):
    """Raised when SKILL.md is missing or its frontmatter can't be parsed."""


def read_frontmatter(skill_md: Path) -> dict[str, Any]:
    """Parse the YAML frontmatter block of a SKILL.md file.

    Frontmatter is the YAML between the first two `---` fence lines at the
    top of the file (skill-authoring-guide.md §2).
    """
    if not skill_md.is_file():
        raise FrontmatterError(f"{skill_md} does not exist")
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError(f"{skill_md}: does not start with a '---' frontmatter fence")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise FrontmatterError(f"{skill_md}: no closing '---' fence found") from None
    fm_text = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"{skill_md}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise FrontmatterError(f"{skill_md}: frontmatter did not parse to a mapping")
    return data


def is_valid_semver(version: Any) -> bool:
    """Strict semver, digits only: MAJOR.MINOR.PATCH. No 'v' prefix, no -rc/+meta."""
    return isinstance(version, str) and bool(SEMVER_RE.match(version))


def semver_tuple(version: str) -> tuple[int, int, int]:
    m = SEMVER_RE.match(version)
    if not m:
        raise ValueError(f"not a valid semver string: {version!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run a git command, returning stripped stdout. Raises on non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def repo_root_from(start: Path) -> Path:
    """Resolve the git repo root containing `start` (file or dir)."""
    top = run_git(["rev-parse", "--show-toplevel"], cwd=start if start.is_dir() else start.parent)
    return Path(top)
