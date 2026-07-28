"""Tests for `de doctor`'s runtime health checks.

The guardrail-seed check is the one that most needs pinning: it asserts that
the five common guardrail cases are present, and it used to do that by
counting `*.mock.yaml` files. Five files of any kind satisfied a count, so a
runtime whose real guardrail suite had been replaced with stubs reported
[PASS] — the check said something stronger than it verified.
"""
from __future__ import annotations

import pytest

from builder.doctor import GUARDRAIL_SEED_FILES, HOOK_FILES, REQUIRED_RUNTIME_FILES, run_checks


def build_runtime_skeleton(tmp_path):
    """A runtime/ that satisfies every check, so tests can break one thing."""
    inst = tmp_path / "inst"
    runtime = inst / "runtime"
    for rel in REQUIRED_RUNTIME_FILES:
        p = runtime / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("rules:\n  - demo\n" if rel.endswith(".yaml") else "{}")
    for rel in HOOK_FILES:
        p = runtime / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/usr/bin/env python3\n")
        p.chmod(0o755)
    for name in ("`.build-manifest.json`", ".build-info.json", ".managed-files.json"):
        (inst / name.strip("`")).write_text("{}")
    tests_dir = runtime / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    for name in GUARDRAIL_SEED_FILES:
        (tests_dir / name).write_text("case: seeded\n")
    (runtime / "work").mkdir(exist_ok=True)
    return inst


def seed_check(inst):
    return next(c for c in run_checks(inst) if c[0].startswith("seeded tests present"))


def test_canonical_seeds_pass(tmp_path):
    inst = build_runtime_skeleton(tmp_path)
    name, passed, detail = seed_check(inst)
    assert passed is True
    assert detail == "all present"


def test_five_impostor_files_do_not_pass(tmp_path):
    """The regression: any five *.mock.yaml files used to satisfy the count."""
    inst = build_runtime_skeleton(tmp_path)
    tests_dir = inst / "runtime" / "tests"
    for name in GUARDRAIL_SEED_FILES:
        (tests_dir / name).unlink()
    for i in range(5):
        (tests_dir / f"junk{i}.mock.yaml").write_text("not_a_guardrail_test: true\n")

    _name, passed, detail = seed_check(inst)
    assert passed is False
    assert "missing" in detail


def test_one_missing_seed_is_named(tmp_path):
    inst = build_runtime_skeleton(tmp_path)
    victim = GUARDRAIL_SEED_FILES[0]
    (inst / "runtime" / "tests" / victim).unlink()

    _name, passed, detail = seed_check(inst)
    assert passed is False
    assert victim in detail


def test_extra_mock_files_alongside_the_seeds_are_fine(tmp_path):
    # A team adding its own cases must not trip the guardrail check.
    inst = build_runtime_skeleton(tmp_path)
    (inst / "runtime" / "tests" / "team-extra-case.mock.yaml").write_text("case: extra\n")
    _name, passed, _detail = seed_check(inst)
    assert passed is True


@pytest.mark.parametrize("hook", HOOK_FILES)
def test_non_executable_hook_is_reported(tmp_path, hook):
    inst = build_runtime_skeleton(tmp_path)
    (inst / "runtime" / hook).chmod(0o644)
    check = next(c for c in run_checks(inst) if c[0] == f"hook executable: {hook}")
    assert check[1] is False
