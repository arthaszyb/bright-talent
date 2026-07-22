from __future__ import annotations

import pytest

from de_eval.frontmatter import FrontmatterError, parse_frontmatter


def write(tmp_path, text):
    p = tmp_path / "SKILL.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_parses_valid_frontmatter(tmp_path):
    p = write(tmp_path, "---\nname: ticket-review\nversion: 0.1.2\n---\n# body\n")
    data = parse_frontmatter(p)
    assert data == {"name": "ticket-review", "version": "0.1.2"}


def test_missing_file_raises(tmp_path):
    with pytest.raises(FrontmatterError, match="not found"):
        parse_frontmatter(tmp_path / "nope.md")


def test_missing_opening_delimiter_raises(tmp_path):
    p = write(tmp_path, "# just markdown\n")
    with pytest.raises(FrontmatterError, match="does not start"):
        parse_frontmatter(p)


def test_unterminated_block_raises(tmp_path):
    p = write(tmp_path, "---\nname: x\n# no closing delimiter\n")
    with pytest.raises(FrontmatterError, match="unterminated"):
        parse_frontmatter(p)


def test_non_mapping_frontmatter_raises(tmp_path):
    p = write(tmp_path, "---\n- a\n- b\n---\n")
    with pytest.raises(FrontmatterError, match="mapping"):
        parse_frontmatter(p)


def test_invalid_yaml_raises(tmp_path):
    p = write(tmp_path, "---\nname: [unclosed\n---\n")
    with pytest.raises(FrontmatterError, match="not valid YAML"):
        parse_frontmatter(p)
