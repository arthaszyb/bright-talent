"""Repo-relative path resolution (ARCHITECTURE.md layout is fixed)."""

from __future__ import annotations

from pathlib import Path

# eval/de_eval/paths.py -> parents[0]=de_eval, [1]=eval, [2]=de-demo
DE_EVAL_ROOT = Path(__file__).resolve().parents[1]
DE_DEMO_ROOT = DE_EVAL_ROOT.parent
SCAFFOLD_ROOT = DE_DEMO_ROOT / "scaffold"
BUILDER_PROJECT = SCAFFOLD_ROOT / "builder"
FIXTURE_INSTANCE_DIR = DE_EVAL_ROOT / "fixture-instance"
FIXTURE_RUNTIME_DIR = FIXTURE_INSTANCE_DIR / "runtime"
FIXTURE_CACHE_FILE = FIXTURE_INSTANCE_DIR / ".de-eval-fixture-cache.json"
RUNS_DIR = DE_EVAL_ROOT / "runs"
JUDGE_TOML = DE_EVAL_ROOT / "judge.toml"

DENY_SET_COMMANDS = ("curl", "wget", "ssh", "kubectl")
