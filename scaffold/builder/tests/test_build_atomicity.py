"""A rejected build must not damage the runtime it rejected.

The safety invariants (permission monotonicity, immutable env keys,
protected MCP servers) are enforced in phases 8-9, after most of the tree
has already been written. Clearing runtime/ up front therefore meant a
*correctly* rejected build still destroyed the previous working runtime and
left a tree with hooks and policy but no settings.json — the file carrying
every deny rule. An instance that tried to escalate and was refused ended up
less protected than before it tried.

The build now stages and swaps, so these pin that a failed build is a no-op
on runtime/.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml

from builder.build import RUNTIME_STAGING_DIRNAME, run_build
from builder.errors import MonotonicityError

REPO = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCAFFOLD = REPO / "scaffold"


@pytest.fixture()
def instance(tmp_path, monkeypatch):
    """A buildable copy of the good fixture, with the scaffold pinned."""
    dst = tmp_path / "inst"
    shutil.copytree(FIXTURES / "good-instance", dst)
    monkeypatch.setenv("DE_SCAFFOLD_ROOT", str(SCAFFOLD))
    return dst


def set_mode(instance_dir: Path, mode: str) -> None:
    path = instance_dir / "instance.yaml"
    data = yaml.safe_load(path.read_text())
    data.setdefault("settings", {}).setdefault("permissions", {})["default_mode"] = mode
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_good_build_produces_a_runtime(instance):
    run_build(instance)
    assert (instance / "runtime" / ".claude" / "settings.json").is_file()
    assert not (instance / RUNTIME_STAGING_DIRNAME).exists()


def test_rejected_build_leaves_the_previous_runtime_intact(instance):
    run_build(instance)
    settings = instance / "runtime" / ".claude" / "settings.json"
    before = settings.read_bytes()

    # Passes schema validation; rejected later by the monotonicity check.
    set_mode(instance, "bypassPermissions")
    with pytest.raises(MonotonicityError):
        run_build(instance)

    assert settings.is_file(), "the failed build destroyed the working runtime"
    assert settings.read_bytes() == before
    assert (instance / "runtime" / ".mcp.json").is_file()


def test_rejected_build_leaves_no_staging_tree(instance):
    run_build(instance)
    set_mode(instance, "bypassPermissions")
    with pytest.raises(MonotonicityError):
        run_build(instance)
    assert not (instance / RUNTIME_STAGING_DIRNAME).exists()


def test_first_build_can_still_fail_without_a_previous_runtime(instance):
    """Nothing to preserve is not an error path of its own."""
    set_mode(instance, "bypassPermissions")
    with pytest.raises(MonotonicityError):
        run_build(instance)
    assert not (instance / "runtime").exists()
    assert not (instance / RUNTIME_STAGING_DIRNAME).exists()


def test_rebuild_after_fixing_the_config_succeeds(instance):
    run_build(instance)
    set_mode(instance, "bypassPermissions")
    with pytest.raises(MonotonicityError):
        run_build(instance)
    # The instance is still recoverable: fix the config and rebuild.
    set_mode(instance, "plan")
    run_build(instance)
    settings = (instance / "runtime" / ".claude" / "settings.json").read_text()
    assert '"defaultMode": "plan"' in settings


def test_stale_staging_tree_does_not_block_a_build(instance):
    stale = instance / RUNTIME_STAGING_DIRNAME
    stale.mkdir()
    (stale / "leftover.txt").write_text("from a killed build")
    run_build(instance)
    assert (instance / "runtime" / ".claude" / "settings.json").is_file()
    assert not (instance / "runtime" / "leftover.txt").exists()
    assert not stale.exists()


def test_staging_dir_is_gitignored():
    # It lives inside the instance tree; an interrupted build must not show
    # up as untracked noise in `git status`.
    assert f"{RUNTIME_STAGING_DIRNAME}/" in (REPO / ".gitignore").read_text()


def test_scaffold_root_env_is_honoured(instance):
    assert os.environ["DE_SCAFFOLD_ROOT"] == str(SCAFFOLD)
