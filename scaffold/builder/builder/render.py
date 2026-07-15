"""Jinja2 rendering — one function per template. StrictUndefined: a missing
variable is a build error, so templates and schema cannot drift apart silently.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

POLICY_FILES = (
    ("security.yaml", "Security (hard DENY rules)"),
    ("sensitive-data.yaml", "Sensitive Data (credential/secret exposure)"),
    ("operation-levels.yaml", "Operation Levels (REQUIRE_APPROVAL rules)"),
    ("change-freeze.yaml", "Change Freeze (team-declared time-based freezes)"),
)


def get_jinja_env(templates_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def build_policy_summary(policy_dir: Path) -> str:
    """Parse the 4 policy YAMLs into a human-readable Markdown summary for
    CLAUDE.md's Policy Summary section."""
    sections: list[str] = []
    for filename, title in POLICY_FILES:
        path = policy_dir / filename
        if not path.is_file():
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        rules = data.get("rules") or []
        sections.append(f"### {title}\n")
        if not rules:
            sections.append("_No active rules._\n")
            continue
        for rule in rules:
            rule_id = rule.get("id", "unknown")
            verdict = rule.get("verdict", "?")
            desc = rule.get("description", "")
            sections.append(f"- **{rule_id}** [{verdict}]: {desc}")
        sections.append("")
    return "\n".join(sections).strip()


def render_claude_md(env: Environment, context: dict) -> str:
    return env.get_template("CLAUDE.md.j2").render(**context)


def render_editor_claude_md(env: Environment, context: dict) -> str:
    return env.get_template("editor-CLAUDE.md.j2").render(**context)


def render_settings_json(env: Environment, context: dict) -> str:
    return env.get_template("settings.json.j2").render(**context)


def render_editor_settings_json(env: Environment, context: dict) -> str:
    return env.get_template("editor-settings.json.j2").render(**context)


def render_mcp_json(env: Environment, context: dict) -> str:
    return env.get_template("mcp.json.j2").render(**context)


def render_bridge_yaml(env: Environment, context: dict) -> str:
    return env.get_template("bridge.yaml.j2").render(**context)
