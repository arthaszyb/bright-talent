"""Build summary: identity, scope, scaffold version, built_at, skills, drift.

Spec: de-cli-spec.md §2.5.
"""

from __future__ import annotations

import json
from pathlib import Path

from builder import validate
from builder.diff import compute_diff
from builder.errors import BuildError


def main(instance_dir: Path, extra: list[str]) -> int:
    build_info_path = instance_dir / ".build-info.json"
    if not build_info_path.is_file():
        raise BuildError("no build found — run `de build` first")
    build_info = json.loads(build_info_path.read_text(encoding="utf-8"))

    config = validate.load_and_validate(instance_dir)
    identity = config["identity"]
    scope = config["scope"]

    skills_lock_path = instance_dir / "skills-lock.json"
    skill_names: list[str] = []
    if skills_lock_path.is_file():
        lock = json.loads(skills_lock_path.read_text(encoding="utf-8"))
        skill_names = sorted((lock.get("skills") or {}).keys())

    print(f"identity:        {identity['id']} ({identity['team']})")
    print(f"scope:           {', '.join(scope['service_catalog'])}")
    print(f"scaffold version: {build_info.get('scaffold_version')}")
    print(f"built_at:        {build_info.get('built_at')}")
    print(f"claude_cli:      {build_info.get('claude_cli_version') or 'not detected'}")
    print(f"skills:          {', '.join(skill_names) if skill_names else '(none)'}")

    try:
        drift = compute_diff(instance_dir)
        clean = not (drift["missing"] or drift["extra"] or drift["modified"])
        print(f"drift:           {'none' if clean else 'DRIFT DETECTED'}")
        if not clean:
            for kind in ("modified", "missing", "extra"):
                for p in drift[kind]:
                    print(f"  {kind}: {p}")
    except BuildError:
        print("drift:           unknown (no manifest)")

    return 0


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
