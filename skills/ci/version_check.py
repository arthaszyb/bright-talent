#!/usr/bin/env python3
"""version-check gate: strict semver, monotonic vs. the latest git tag, and
a matching CHANGELOG.md heading.

Rules (release-and-ci.md §2, §11):
  - SKILL.md's `version:` must be valid strict semver.
  - It must be strictly greater than the latest `<name>/v*` git tag (numeric
    comparison, not lexical — `0.10.0 > 0.9.0`). No tags yet -> any valid
    semver passes (first release).
  - CHANGELOG.md must contain a heading for the current version.

Usage:
    uv run --project skills/ci python skills/ci/version_check.py <skill-dir>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    FrontmatterError,
    is_valid_semver,
    read_frontmatter,
    run_git,
    semver_tuple,
)

TAG_RE = re.compile(r"^(?P<name>.+)/v(?P<version>\d+\.\d+\.\d+)$")


def latest_tag_version(skill_name: str, cwd: Path) -> str | None:
    try:
        output = run_git(["tag", "--list", f"{skill_name}/v*"], cwd=cwd)
    except RuntimeError as exc:
        print(f"version-check: could not list git tags: {exc}")
        return None
    versions: list[tuple[int, int, int]] = []
    version_strs: dict[tuple[int, int, int], str] = {}
    for line in output.splitlines():
        m = TAG_RE.match(line.strip())
        if not m or m.group("name") != skill_name:
            continue
        v = m.group("version")
        if is_valid_semver(v):
            t = semver_tuple(v)
            versions.append(t)
            version_strs[t] = v
    if not versions:
        return None
    return version_strs[max(versions)]


def changelog_has_heading(changelog: Path, version: str) -> bool:
    if not changelog.is_file():
        return False
    heading_re = re.compile(r"^#{1,6}\s.*\b" + re.escape(version) + r"\b")
    for line in changelog.read_text(encoding="utf-8").splitlines():
        if heading_re.match(line.strip()):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path, help="path to a skills/<name>/ directory")
    args = parser.parse_args()

    skill_dir: Path = args.skill_dir
    violations: list[str] = []

    try:
        fm = read_frontmatter(skill_dir / "SKILL.md")
    except FrontmatterError as exc:
        print(f"version-check fail: {exc}")
        return 1

    name = fm.get("name") or skill_dir.name
    version = fm.get("version")

    if not is_valid_semver(version):
        violations.append(f"version {version!r} is not strict semver (MAJOR.MINOR.PATCH)")
    else:
        latest = latest_tag_version(name, cwd=skill_dir)
        if latest is not None:
            if semver_tuple(version) <= semver_tuple(latest):
                violations.append(
                    f"version {version} is not strictly greater than latest tag "
                    f"{name}/v{latest}"
                )

    changelog = skill_dir / "CHANGELOG.md"
    if is_valid_semver(version) and not changelog_has_heading(changelog, version):
        violations.append(
            f"CHANGELOG.md has no heading for version {version} "
            f"(expected a line like '## {version}')"
        )

    if violations:
        for v in violations:
            print(f"version-check fail: {v}")
        return 1

    print(f"version-check ok: {name}/v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
