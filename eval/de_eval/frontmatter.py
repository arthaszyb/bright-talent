"""SKILL.md YAML-frontmatter parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class FrontmatterError(Exception):
    pass


def parse_frontmatter(md_path: Path) -> dict[str, Any]:
    """Parse the `---\\n...\\n---` frontmatter block at the top of md_path."""
    if not md_path.is_file():
        raise FrontmatterError(f"not found: {md_path}")
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError(f"{md_path}: does not start with a '---' frontmatter block")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise FrontmatterError(f"{md_path}: unterminated frontmatter block (no closing '---')")
    block = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as e:
        raise FrontmatterError(f"{md_path}: frontmatter is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise FrontmatterError(f"{md_path}: frontmatter must parse to a mapping")
    return data
