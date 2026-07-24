import pytest

from console.drafts import OP_CONFIG_EDIT, is_allowed, is_forbidden, is_safe_relative_path


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


@pytest.mark.parametrize("path", [
    "kb/team/../../../../tmp/pwned",      # escapes the whole workspace
    "kb/team/../../instance.yaml",        # traversal back into a real file
    "kb/team/../../../etc/cron.d/x",
    "kb/team/./../../secret",
    "/etc/passwd",                        # absolute
    "/kb/team/x.md",
    "kb/team/sub/../../../out",
    "..",
    ".",
    "kb\\team\\x.md",                     # backslash separator
    " kb/team/x.md",                      # leading whitespace
    "",
])
def test_traversal_and_absolute_paths_are_rejected(path):
    # The allowlist prefix rule (kb/team/) must not admit paths that escape
    # the instance tree via `..`, a leading slash, or backslash separators.
    assert is_safe_relative_path(path) is False
    assert is_allowed(OP_CONFIG_EDIT, path) is False


@pytest.mark.parametrize("path", [
    "instance.yaml",
    "kb/team/_index.md",
    "kb/team/sub/deep/ok.md",
])
def test_plain_relative_paths_are_safe(path):
    assert is_safe_relative_path(path) is True
