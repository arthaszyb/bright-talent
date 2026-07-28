"""Tests for PATH-shim generation (de_eval/shim.py).

The shims are what make strict replay a real boundary rather than a claim:
the shim dir is prepended to PATH, so a command with a shim is intercepted
and replayed, and anything the deny-set covers can never reach the network.
These pin the name derivation and, in particular, that a shim can never be
written outside the shim directory.
"""
from __future__ import annotations

import stat

import pytest

from de_eval.fixture_server import FixtureFileError
from de_eval.paths import DENY_SET_COMMANDS
from de_eval.shim import first_words, shim_names_for_case, write_shims


def fx(prefix):
    return {"command_prefix": prefix}


# ---- first_words -----------------------------------------------------------

def test_first_word_of_each_prefix():
    assert first_words([fx("uv run python a.py"), fx("git status")]) == {"uv", "git"}


def test_blank_and_missing_prefixes_are_skipped():
    # The trailing catch-all fixture carries no prefix and names no shim.
    assert first_words([fx(""), fx(None), {}]) == set()


def test_duplicate_first_words_collapse():
    assert first_words([fx("uv run a"), fx("uv run b")]) == {"uv"}


@pytest.mark.parametrize("prefix", [
    "/usr/bin/git commit",     # absolute: pathlib would discard the shim dir
    "./tool run",              # relative path invocation
    "../../bin/tool run",      # traversal
    "bin/tool run",            # nested path
])
def test_path_invocations_are_rejected(prefix):
    # A command invoked by path skips PATH lookup entirely, so no shim could
    # intercept it — accepting the fixture would promise isolation that does
    # not exist.
    with pytest.raises(FixtureFileError, match="bare command name"):
        first_words([fx(prefix)])


# ---- shim_names_for_case ---------------------------------------------------

def test_deny_set_is_always_included():
    names = shim_names_for_case([fx("uv run a")])
    assert set(DENY_SET_COMMANDS) <= names
    assert "uv" in names


def test_fallback_only_case_still_gets_the_deny_set():
    # A catch-all-only fixture list names no command of its own; the deny-set
    # is the only interception it gets. Pinning this documents the real
    # boundary rather than implying blanket coverage.
    assert shim_names_for_case([fx("")]) == set(DENY_SET_COMMANDS)


# ---- write_shims -----------------------------------------------------------

def test_writes_executable_shims_inside_the_dir(tmp_path):
    shim_dir = tmp_path / "shims"
    written = write_shims(shim_dir, {"uv", "curl"})
    assert sorted(p.name for p in written) == ["curl", "uv"]
    for p in written:
        assert p.parent == shim_dir
        assert p.stat().st_mode & stat.S_IXUSR
        assert "DE_EVAL_FIXTURE_SOCK" in p.read_text()


def test_absolute_shim_name_cannot_escape_the_dir(tmp_path):
    # pathlib drops the left operand when the right is absolute, so an
    # unguarded `shim_dir / name` would write over the real binary's path.
    shim_dir = tmp_path / "shims"
    with pytest.raises(FixtureFileError, match="outside the shim directory"):
        write_shims(shim_dir, {"/usr/bin/git"})


def test_traversal_shim_name_cannot_escape_the_dir(tmp_path):
    shim_dir = tmp_path / "shims"
    with pytest.raises(FixtureFileError, match="outside the shim directory"):
        write_shims(shim_dir, {"../escaped"})
    assert not (tmp_path / "escaped").exists()
