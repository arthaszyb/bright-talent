import pytest

from console.drafts import OP_CONFIG_EDIT, is_allowed, is_forbidden


@pytest.mark.parametrize("path", [
    "runtime/CLAUDE.md",
    "runtime/.claude/settings.json",
    ".env",
    ".env.production",
    ".claude/policy/security.yaml",
    ".claude/policy-overrides.yaml",  # prefix match, not just directory
    ".claude/hooks/skill-gate.py",
    "commands/whatever.py",
    "agents/x.yaml",
    "tools/y.py",
])
def test_forbidden_paths(path):
    assert is_forbidden(path) is True
    assert is_allowed(OP_CONFIG_EDIT, path) is False


def test_env_example_is_not_forbidden():
    assert is_forbidden(".env.example") is False


@pytest.mark.parametrize("path", [
    "instance.yaml",
    "skills.yaml",
    "kb/team/_index.md",
    "kb/team/ok.md",
    ".env.example",
    "README.md",
    ".gitignore",
])
def test_config_edit_allowed_paths(path):
    assert is_allowed(OP_CONFIG_EDIT, path) is True


@pytest.mark.parametrize("path", [
    "kb/change-management-principles.md",  # base kb, not team kb
    "VERSION",
    "Makefile",
    "skills-lock.json",
    "editor/CLAUDE.md",
])
def test_config_edit_disallowed_paths_outside_allowlist(path):
    assert is_allowed(OP_CONFIG_EDIT, path) is False
