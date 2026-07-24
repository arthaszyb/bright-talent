#!/usr/bin/env python3
"""detect-release gate: has every changed skill bumped its version?

Iron rule #1 (release-and-ci.md §1): any change under `skills/skills/<name>/`
requires a `version:` bump in that skill's SKILL.md in the same range, or
this gate blocks the merge.

Usage:
    uv run --project skills/ci python skills/ci/detect_release.py \\
        [--base <git-ref>] [--head <git-ref>]

Must be run with cwd inside the git repo that hosts the `skills/` registry
(the acceptance harness runs it from the `de-demo/` repo root). Skill
directories are discovered under `skills/skills/<name>/`, matching this
demo's actual on-disk layout (see `skills/README.md`).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import FrontmatterError, run_git  # noqa: E402

SKILLS_SUBPATH = "skills/skills"


def git_show(ref: str, path: str, cwd: Path) -> str | None:
    """Return file contents of `path` at `ref`, or None if it doesn't exist there."""
    import subprocess

    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def version_at(ref: str, skill_name: str, repo_root: Path) -> str | None:
    """SKILL.md `version:` for `skill_name` as of `ref`, or None if the file
    doesn't exist at that ref (new or deleted skill)."""
    rel_path = f"{SKILLS_SUBPATH}/{skill_name}/SKILL.md"
    content = git_show(ref, rel_path, repo_root)
    if content is None:
        return None
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError(f"{rel_path}@{ref}: missing frontmatter fence")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise FrontmatterError(f"{rel_path}@{ref}: no closing frontmatter fence") from None
    import yaml

    fm = yaml.safe_load("\n".join(lines[1:end])) or {}
    return fm.get("version")


def changed_skill_names(base: str, head: str, repo_root: Path) -> set[str]:
    """Skill directory names touched by the diff between `base` and `head`."""
    diff_output = run_git(["diff", "--name-only", base, head], cwd=repo_root)
    changed_files = [line for line in diff_output.splitlines() if line.strip()]

    skill_names: set[str] = set()
    prefix = f"{SKILLS_SUBPATH}/"
    for f in changed_files:
        if not f.startswith(prefix):
            continue
        rest = f[len(prefix):]
        parts = rest.split("/", 1)
        if parts and parts[0]:
            skill_names.add(parts[0])
    return skill_names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD~1", help="base git ref (default: HEAD~1)")
    parser.add_argument("--head", default="HEAD", help="head git ref (default: HEAD)")
    parser.add_argument(
        "--changed-json",
        action="store_true",
        help="print a JSON array of changed skill names and exit 0 (for a dynamic "
        "CI matrix); does not run the version-bump gate",
    )
    args = parser.parse_args()

    repo_root = Path(run_git(["rev-parse", "--show-toplevel"]))

    skill_names = changed_skill_names(args.base, args.head, repo_root)

    if args.changed_json:
        import json

        print(json.dumps(sorted(skill_names)))
        return 0

    if not skill_names:
        print("no skill changes")
        return 0

    offenders: list[str] = []
    releases: list[str] = []
    for name in sorted(skill_names):
        try:
            base_version = version_at(args.base, name, repo_root)
        except FrontmatterError as exc:
            offenders.append(f"{name}: could not read version at base ref: {exc}")
            continue
        try:
            head_version = version_at(args.head, name, repo_root)
        except FrontmatterError as exc:
            offenders.append(f"{name}: could not read version at head ref: {exc}")
            continue

        if head_version is None:
            offenders.append(
                f"{name}: SKILL.md missing at head ref {args.head!r} "
                "(skill deletion requires a coordinated maintainer override, "
                "not a plain CI pass — see release-and-ci.md §9)"
            )
            continue

        if base_version is None:
            # New skill introduced in this range: any version counts as the release.
            releases.append(f"release: {name}/v{head_version}")
            continue

        if head_version == base_version:
            offenders.append(
                f"{name}: changed between {args.base} and {args.head} but "
                f"version did not bump (still {base_version})"
            )
            continue

        releases.append(f"release: {name}/v{head_version}")

    if offenders:
        for line in offenders:
            print(line)
        return 1

    for line in releases:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
