"""Unit tests for skill resolution + description parsing (builder/skills.py).

The skill supply chain is security-relevant (what code lands in the agent's
runtime). These pin the pure resolution behavior; the git-pin path is
exercised against a throwaway repo.
"""
from __future__ import annotations

import subprocess

from builder import skills

# ---- _skill_description / frontmatter --------------------------------------

FRONTMATTER_SKILL = """---
name: demo-skill
version: 1.0.0
description: Does the thing well. Use ONLY when asked. Do NOT otherwise.
---
# Demo Skill
body line
"""


def write_skill(tmp_path, text):
    d = tmp_path / "demo-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    return d


def test_description_uses_frontmatter_first_sentence(tmp_path):
    d = write_skill(tmp_path, FRONTMATTER_SKILL)
    assert skills._skill_description(d) == "Does the thing well."


def test_description_does_not_return_frontmatter_name_line(tmp_path):
    # Regression: the old heuristic returned "name: demo-skill".
    d = write_skill(tmp_path, FRONTMATTER_SKILL)
    assert "name:" not in skills._skill_description(d)


def test_description_falls_back_to_body_line(tmp_path):
    d = write_skill(tmp_path, "---\nname: x\n---\n# Heading\nActual body sentence.\n")
    assert skills._skill_description(d) == "Actual body sentence."


def test_description_missing_file(tmp_path):
    d = tmp_path / "demo-skill"
    d.mkdir()
    assert skills._skill_description(d) == "demo-skill skill"


def test_frontmatter_parses_and_tolerates_absence():
    assert skills._frontmatter("---\na: 1\n---\nbody")["a"] == 1
    assert skills._frontmatter("no frontmatter here") == {}
    assert skills._frontmatter("---\nnot: [closed\n---\n") == {}


# ---- _sha256_tree determinism ----------------------------------------------

def test_sha256_tree_is_order_independent(tmp_path):
    a = tmp_path / "a"
    (a / "sub").mkdir(parents=True)
    (a / "z.txt").write_text("z")
    (a / "sub" / "b.txt").write_text("b")
    first = skills._sha256_tree(a)
    # Same content, files created in a different order -> identical hash.
    b = tmp_path / "b"
    (b / "sub").mkdir(parents=True)
    (b / "sub" / "b.txt").write_text("b")
    (b / "z.txt").write_text("z")
    assert skills._sha256_tree(b) == first


def test_sha256_tree_changes_with_content(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "f.txt").write_text("one")
    h1 = skills._sha256_tree(a)
    (a / "f.txt").write_text("two")
    assert skills._sha256_tree(a) != h1


# ---- resolve_and_install ---------------------------------------------------

def _init_registry(tmp_path):
    """A git registry with skills/demo-skill/SKILL.md, tagged demo-skill/v1.0.0."""
    reg = tmp_path / "registry"
    skill = reg / "skills" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(FRONTMATTER_SKILL, encoding="utf-8")
    (skill / "run.py").write_text("print('hi')\n", encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    import os
    env = {**os.environ, **env}
    subprocess.run(["git", "init", "-q"], cwd=reg, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=reg, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=reg, check=True, env=env)
    subprocess.run(["git", "tag", "demo-skill/v1.0.0"], cwd=reg, check=True, env=env)
    return reg


def test_resolve_installs_skill_files_and_writes_lock(tmp_path):
    _init_registry(tmp_path)
    # Build an instance whose file://../registry resolves to the registry above.
    instance = tmp_path / "instance"
    instance.mkdir()
    (instance / "skills.yaml").write_text(
        "registries:\n  local:\n    url: \"file://../registry\"\n"
        "default_registry: local\n"
        "dependencies:\n  demo-skill:\n    registry: local\n    tag: \"demo-skill/v1.0.0\"\n",
        encoding="utf-8",
    )
    runtime = instance / "runtime"
    runtime.mkdir()

    skills_tmpl, manifest, warnings = skills.resolve_and_install(instance, runtime)

    assert warnings == []
    assert skills_tmpl == [{"name": "demo-skill", "description": "Does the thing well."}]
    installed = {e["path"] for e in manifest}
    assert ".claude/skills/demo-skill/SKILL.md" in installed
    assert ".claude/skills/demo-skill/run.py" in installed

    import json
    lock = json.loads((instance / "skills-lock.json").read_text())
    entry = lock["skills"]["demo-skill"]
    assert entry["version"] == "demo-skill/v1.0.0"
    assert entry["commit"] and len(entry["commit"]) == 40  # tag resolved to a commit
    assert entry["integrity"].startswith("sha256:")


def test_resolve_skips_missing_registry_with_warning(tmp_path):
    instance = tmp_path / "instance"
    instance.mkdir()
    (instance / "skills.yaml").write_text(
        "registries:\n  local:\n    url: \"file://../does-not-exist\"\n"
        "default_registry: local\n"
        "dependencies:\n  demo-skill:\n    registry: local\n    tag: \"x\"\n",
        encoding="utf-8",
    )
    runtime = instance / "runtime"
    runtime.mkdir()
    skills_tmpl, manifest, warnings = skills.resolve_and_install(instance, runtime)
    assert skills_tmpl == [] and manifest == []
    assert any("registry path" in w for w in warnings)


def test_resolve_no_skills_yaml_is_empty(tmp_path):
    instance = tmp_path / "instance"
    instance.mkdir()
    runtime = instance / "runtime"
    runtime.mkdir()
    skills_tmpl, manifest, warnings = skills.resolve_and_install(instance, runtime)
    assert skills_tmpl == [] and manifest == []
