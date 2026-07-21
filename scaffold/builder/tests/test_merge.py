"""Unit tests for the merge invariants (builder/merge.py).

These four pure functions are the safety floor of multi-tenant composition:
permission monotonicity, immutable base env, protected MCP servers, and the
no-shadowing rule. Spec: docs/10-scaffold/design.md §4.
"""
from __future__ import annotations

import pytest

from builder.errors import BuildConflictError, MonotonicityError
from builder.merge import (
    BASE_DEFAULT_MODE,
    PERMISSION_STRICTNESS,
    check_env_immutable,
    check_monotonic_mode,
    merge_directory_map,
    merge_disable_servers,
)


class TestCheckMonotonicMode:
    def test_none_returns_base_mode(self):
        assert check_monotonic_mode(None) == BASE_DEFAULT_MODE

    def test_same_mode_is_allowed(self):
        assert check_monotonic_mode(BASE_DEFAULT_MODE) == BASE_DEFAULT_MODE

    @pytest.mark.parametrize("stricter", ["plan", "default"])
    def test_stricter_modes_are_allowed(self, stricter):
        assert check_monotonic_mode(stricter) == stricter

    def test_looser_mode_raises(self):
        with pytest.raises(MonotonicityError, match="less restrictive"):
            check_monotonic_mode("bypassPermissions")

    def test_unknown_mode_raises(self):
        with pytest.raises(MonotonicityError, match="not a valid"):
            check_monotonic_mode("yolo")

    def test_every_mode_relative_to_strictest_base(self):
        # With the strictest possible base, only that mode itself passes.
        base = PERMISSION_STRICTNESS[0]
        assert check_monotonic_mode(base, base_mode=base) == base
        for looser in PERMISSION_STRICTNESS[1:]:
            with pytest.raises(MonotonicityError):
                check_monotonic_mode(looser, base_mode=base)


class TestCheckEnvImmutable:
    def test_disjoint_overlay_passes_through(self):
        overlay = {"MY_VAR": "1", "OTHER": "x"}
        assert check_env_immutable(overlay) == overlay

    def test_none_and_empty_are_fine(self):
        assert check_env_immutable(None) == {}
        assert check_env_immutable({}) == {}

    def test_base_key_collision_raises(self):
        with pytest.raises(BuildConflictError, match="CHANGE_GATEWAY_BASE"):
            check_env_immutable({"CHANGE_GATEWAY_BASE": "http://evil.acme.example"})

    def test_collision_message_lists_all_offenders(self):
        keys = frozenset({"A", "B"})
        with pytest.raises(BuildConflictError, match=r"\['A', 'B'\]"):
            check_env_immutable({"B": "2", "A": "1", "C": "3"}, base_keys=keys)


class TestMergeDisableServers:
    def test_protected_server_is_never_disabled(self):
        assert merge_disable_servers(["de-agent-escalate"]) == []

    def test_unprotected_servers_pass_through_in_order(self):
        req = ["b-server", "de-agent-escalate", "a-server"]
        assert merge_disable_servers(req) == ["b-server", "a-server"]

    def test_none_and_empty(self):
        assert merge_disable_servers(None) == []
        assert merge_disable_servers([]) == []


class TestMergeDirectoryMap:
    def test_disjoint_maps_merge(self):
        base = {"hooks/gate.py": "base"}
        overlay = {"kb/team/sop.md": "instance"}
        merged = merge_directory_map(base, overlay, "instance kb/")
        assert merged == {"hooks/gate.py": "base", "kb/team/sop.md": "instance"}

    def test_shadowing_base_path_raises(self):
        base = {"hooks/gate.py": "base", "policy/net.yaml": "base"}
        overlay = {"hooks/gate.py": "instance"}
        with pytest.raises(BuildConflictError, match=r"hooks/gate\.py"):
            merge_directory_map(base, overlay, "instance kb/")

    def test_error_names_the_overlay_source(self):
        with pytest.raises(BuildConflictError, match="instance kb/"):
            merge_directory_map({"x": "base"}, {"x": "instance"}, "instance kb/")

    def test_inputs_are_not_mutated(self):
        base = {"a": "base"}
        overlay = {"b": "instance"}
        merge_directory_map(base, overlay, "src")
        assert base == {"a": "base"} and overlay == {"b": "instance"}
