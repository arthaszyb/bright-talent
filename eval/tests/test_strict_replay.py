"""Unit tests for the strict-replay execution axis: fixture matching and
PATH-shim generation (eval-spec.md §5.4)."""
from __future__ import annotations

import os

import pytest

from de_eval.fixture_server import FixtureFileError, match_fixture, validate_fixtures
from de_eval.paths import DENY_SET_COMMANDS
from de_eval.shim import first_words, shim_names_for_case, write_shims


def fx(prefix, stdout=""):
    return {"command_prefix": prefix, "stdout": stdout, "stderr": "", "exit_code": 0}


class TestMatchFixture:
    def test_prefix_match_in_declaration_order(self):
        fixtures = [fx("uv run python scripts/a.py"), fx("uv run")]
        matched, fallback = match_fixture(fixtures, "uv run python scripts/a.py --json")
        assert matched is fixtures[0] and fallback is False

    def test_no_match_returns_none(self):
        matched, fallback = match_fixture([fx("kubectl get")], "curl https://x.acme.example")
        assert matched is None and fallback is False

    def test_empty_prefix_is_fallback(self):
        fixtures = [fx("kubectl get"), fx("", stdout="default")]
        matched, fallback = match_fixture(fixtures, "anything at all")
        assert matched is fixtures[1] and fallback is True

    def test_unmatched_is_strict_no_implicit_fallback(self):
        # Without an explicit '' fallback, a near-miss must NOT match: the
        # shim then exits 97 and the case fails closed.
        matched, _ = match_fixture([fx("uv run python scripts/a.py")], "uv run python other.py")
        assert matched is None


class TestValidateFixtures:
    def test_fallback_must_be_last(self):
        with pytest.raises(FixtureFileError, match="unreachable fixture"):
            validate_fixtures([fx(""), fx("kubectl get")])

    def test_fallback_last_is_valid(self):
        validate_fixtures([fx("kubectl get"), fx("")])

    def test_empty_list_is_valid(self):
        validate_fixtures([])


class TestShims:
    def test_first_words_dedupe_and_skip_blank(self):
        fixtures = [fx("uv run a"), fx("uv run b"), fx("kubectl get"), fx(""), fx("   ")]
        assert first_words(fixtures) == {"uv", "kubectl"}

    def test_deny_set_always_included(self):
        names = shim_names_for_case([fx("uv run a")])
        assert set(DENY_SET_COMMANDS) <= names
        assert "uv" in names

    def test_write_shims_creates_executables(self, tmp_path):
        written = write_shims(tmp_path / "shims", {"uv", "curl"})
        assert sorted(p.name for p in written) == ["curl", "uv"]
        for p in written:
            assert os.access(p, os.X_OK)
            assert p.read_text().startswith("#!/usr/bin/env python3")
