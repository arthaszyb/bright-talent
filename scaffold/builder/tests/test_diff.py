"""Unit tests for drift detection (builder/diff.py)."""
from __future__ import annotations

import hashlib
import json

import pytest

from builder.diff import compute_diff
from builder.errors import BuildError


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def make_instance(tmp_path, manifest_files, runtime_files):
    """manifest_files: {path: content}; runtime_files: {path: content}."""
    inst = tmp_path / "inst"
    (inst / "runtime").mkdir(parents=True)
    entries = [{"path": p, "sha256": _sha(c), "source": "template"} for p, c in manifest_files.items()]
    (inst / ".build-manifest.json").write_text(json.dumps({"files": entries}))
    for p, c in runtime_files.items():
        fp = inst / "runtime" / p
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(c)
    return inst


def test_no_manifest_raises(tmp_path):
    (tmp_path / "runtime").mkdir()
    with pytest.raises(BuildError, match="no build manifest"):
        compute_diff(tmp_path)


def test_clean_runtime_has_no_drift(tmp_path):
    inst = make_instance(tmp_path, {"CLAUDE.md": "hi"}, {"CLAUDE.md": "hi"})
    assert compute_diff(inst) == {"missing": [], "extra": [], "modified": [], "mode_changed": []}


def test_modified_file_detected(tmp_path):
    inst = make_instance(tmp_path, {"CLAUDE.md": "hi"}, {"CLAUDE.md": "changed"})
    assert compute_diff(inst)["modified"] == ["CLAUDE.md"]


def test_missing_and_extra_detected(tmp_path):
    inst = make_instance(tmp_path, {"a.txt": "a"}, {"b.txt": "b"})
    d = compute_diff(inst)
    assert d["missing"] == ["a.txt"] and d["extra"] == ["b.txt"]


def test_runtime_work_state_is_not_drift(tmp_path):
    # Regression: after the agent runs, runtime/work/ holds hook state that
    # was never part of the build — it must NOT be reported as extra drift.
    inst = make_instance(
        tmp_path,
        {"CLAUDE.md": "hi"},
        {"CLAUDE.md": "hi", "work/.skill-gate/sess.flag": "", "work/log.txt": "x"},
    )
    assert compute_diff(inst) == {"missing": [], "extra": [], "modified": [], "mode_changed": []}


def test_non_work_extra_still_flagged(tmp_path):
    # A stray file outside the runtime-state dirs is still real drift.
    inst = make_instance(tmp_path, {"CLAUDE.md": "hi"}, {"CLAUDE.md": "hi", "rogue.txt": "x"})
    assert compute_diff(inst)["extra"] == ["rogue.txt"]


# ---- executable-bit drift ---------------------------------------------------
#
# The security hooks only run if they are executable, so `chmod -x` on one
# disables a guardrail without changing a byte. Hash comparison alone cannot
# see that, and `de doctor` already treats hook executability as a check —
# `de diff`, the drift contract, must not be the blind one.


def make_exec_instance(tmp_path, executable_in_manifest: bool, executable_on_disk: bool):
    inst = tmp_path / "inst"
    (inst / "runtime" / ".claude" / "hooks").mkdir(parents=True)
    hook_rel = ".claude/hooks/escalation-guard.py"
    body = "#!/usr/bin/env python3\n"
    entry = {
        "path": hook_rel,
        "sha256": _sha(body),
        "source": "base",
        "executable": executable_in_manifest,
    }
    (inst / ".build-manifest.json").write_text(json.dumps({"files": [entry]}))
    fp = inst / "runtime" / hook_rel
    fp.write_text(body)
    fp.chmod(0o755 if executable_on_disk else 0o644)
    return inst, hook_rel


def test_hook_stripped_of_executable_bit_is_drift(tmp_path):
    inst, hook = make_exec_instance(tmp_path, executable_in_manifest=True, executable_on_disk=False)
    d = compute_diff(inst)
    assert d["mode_changed"] == [hook]
    assert d["modified"] == []  # content is untouched


def test_matching_executable_bit_is_not_drift(tmp_path):
    inst, _ = make_exec_instance(tmp_path, executable_in_manifest=True, executable_on_disk=True)
    assert compute_diff(inst)["mode_changed"] == []


def test_newly_executable_file_is_drift(tmp_path):
    inst, hook = make_exec_instance(tmp_path, executable_in_manifest=False, executable_on_disk=True)
    assert compute_diff(inst)["mode_changed"] == [hook]


def test_manifest_without_executable_field_reports_no_mode_drift(tmp_path):
    # Backwards compatibility: a manifest written before the field existed
    # says nothing about mode, and unknown must not be reported as changed.
    inst = tmp_path / "inst"
    (inst / "runtime").mkdir(parents=True)
    body = "x"
    (inst / ".build-manifest.json").write_text(
        json.dumps({"files": [{"path": "a.sh", "sha256": _sha(body), "source": "base"}]})
    )
    fp = inst / "runtime" / "a.sh"
    fp.write_text(body)
    fp.chmod(0o755)
    assert compute_diff(inst)["mode_changed"] == []
