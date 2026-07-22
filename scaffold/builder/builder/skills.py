"""Skill dependency resolution + install into runtime/.claude/skills/.

Demo form (DESIGN.md S4): skills.yaml declares `registries` (name -> {url}),
`default_registry`, and `dependencies` (name -> {registry, tag|commit}).
Registries are local `file://` paths, resolved relative to the instance dir
(matching ARCHITECTURE.md's `base.repo: file://../../scaffold` convention).

If the registry path does not exist yet (skills land in a later wave), the
dependency is skipped with a warning on stderr — build must still succeed
with an empty skill list.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

LOCK_FILENAME = "skills-lock.json"


def _file_url_to_path(instance_dir: Path, url: str) -> Path | None:
    if not url.startswith("file://"):
        return None
    rel = url[len("file://") :]
    return (instance_dir / rel).resolve()


def load_skills_yaml(instance_dir: Path) -> dict:
    path = instance_dir / "skills.yaml"
    if not path.is_file():
        return {"registries": {}, "default_registry": None, "dependencies": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("registries", {})
    data.setdefault("dependencies", {})
    data.setdefault("default_registry", None)
    return data


def _frontmatter(text: str) -> dict:
    """Parse the leading `---\\n...\\n---` YAML frontmatter block; {} if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                data = yaml.safe_load("\n".join(lines[1:i]))
            except yaml.YAMLError:
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def _first_sentence(text: str) -> str:
    """First sentence of `text` (up to the first '. '), else the whole string."""
    m = re.match(r"\s*(.+?\.)(?:\s|$)", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


def _skill_description(skill_dir: Path) -> str:
    """The skill's one-line description for the CLAUDE.md skill index.

    Prefers the SKILL.md frontmatter `description` field (first sentence, to
    keep the index concise — the full routing text lives in SKILL.md itself);
    falls back to the first non-heading body line, then to '<name> skill'.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return f"{skill_dir.name} skill"
    text = skill_md.read_text(encoding="utf-8")

    desc = _frontmatter(text).get("description")
    if isinstance(desc, str) and desc.strip():
        return _first_sentence(desc)

    # Fallback: first non-heading line of the body (after any frontmatter).
    body = text
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body = "\n".join(lines[i + 1 :])
                break
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return f"{skill_dir.name} skill"


def _sha256_tree(directory: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(directory)).encode("utf-8"))
            h.update(path.read_bytes())
    return h.hexdigest()


def _git_commit(path: Path, ref: str | None) -> str | None:
    """Resolve `ref` (a tag or commit pin) to a commit hash inside the repo
    that contains `path`. `ref=None` falls back to HEAD, which only makes
    sense for an unpinned ("latest") dependency."""
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", f"{ref or 'HEAD'}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def resolve_and_install(
    instance_dir: Path, runtime_dir: Path
) -> tuple[list[dict], list[dict], list[str]]:
    """Returns (skills_for_template, manifest_entries, warnings).

    skills_for_template: [{"name": str, "description": str}]
    manifest_entries: [{"path": <runtime-relative>, "sha256": ..., "source": "instance"}]
    """
    manifest = load_skills_yaml(instance_dir)
    dependencies: dict[str, Any] = manifest.get("dependencies") or {}
    registries: dict[str, Any] = manifest.get("registries") or {}
    default_registry = manifest.get("default_registry")

    skills_for_template: list[dict] = []
    manifest_entries: list[dict] = []
    warnings: list[str] = []
    lock_skills: dict[str, Any] = {}

    skills_dest_root = runtime_dir / ".claude" / "skills"

    for dep_name, dep_spec in dependencies.items():
        dep_spec = dep_spec or {}
        registry_name = dep_spec.get("registry", default_registry)
        registry = registries.get(registry_name, {})
        url = registry.get("url")
        if not url:
            warnings.append(
                f"skills: dependency '{dep_name}' has no resolvable registry url; skipping"
            )
            continue
        registry_path = _file_url_to_path(instance_dir, url)
        if registry_path is None or not registry_path.is_dir():
            warnings.append(
                f"skills: registry path for '{dep_name}' not found ({url}) — "
                "skills land in a later wave; skipping"
            )
            continue

        # A registry repo is scanned for **/skills/<name>/SKILL.md (skills-yaml-spec.md §1).
        candidates = list(registry_path.glob(f"**/skills/{dep_name}/SKILL.md"))
        if not candidates:
            candidates = list(registry_path.glob(f"**/{dep_name}/SKILL.md"))
        if not candidates:
            warnings.append(
                f"skills: could not locate skill '{dep_name}' under registry {registry_path}; skipping"
            )
            continue

        skill_dir = candidates[0].parent
        dest_dir = skills_dest_root / dep_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        for src_file in sorted(skill_dir.rglob("*")):
            if src_file.is_file():
                rel = src_file.relative_to(skill_dir)
                dst_file = dest_dir / rel
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                dst_file.write_bytes(src_file.read_bytes())
                manifest_entries.append(
                    {
                        "path": str((dest_dir / rel).relative_to(runtime_dir)),
                        "sha256": hashlib.sha256(src_file.read_bytes()).hexdigest(),
                        "source": "instance",
                    }
                )

        skills_for_template.append(
            {"name": dep_name, "description": _skill_description(skill_dir)}
        )
        pin = dep_spec.get("tag") or dep_spec.get("commit")
        lock_skills[dep_name] = {
            "version": pin or "latest",
            "commit": _git_commit(skill_dir, pin),
            "integrity": f"sha256:{_sha256_tree(skill_dir)}",
        }

    lock_path = instance_dir / LOCK_FILENAME
    lock_path.write_text(
        json.dumps({"skills": lock_skills}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    return skills_for_template, manifest_entries, warnings


def main(instance_dir: Path, extra: list[str]) -> int:
    runtime_dir = instance_dir / "runtime"
    if not runtime_dir.is_dir():
        print(
            "error: runtime/ not found — run `de build` before `de skills`", file=sys.stderr
        )
        return 1
    skills, _entries, _warnings = resolve_and_install(instance_dir, runtime_dir)
    if not skills:
        print("no skills installed.")
    else:
        for s in skills:
            print(f"- {s['name']}: {s['description']}")
    return 0


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
