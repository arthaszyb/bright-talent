"""Behavioral tests for the escalation-guard circuit-breaker hook.

Driven as a subprocess with hook JSON on stdin, exactly as the agent harness
runs it. Covers: fail-open on bad input, PreToolUse deny of an already-
escalated call, repeated-attempt escalation with a well-formed timestamp, and
robustness against structured (non-string) tool output.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "base" / ".claude" / "hooks" / "escalation-guard.py"


def run_hook(payload, project_dir, env_extra=None):
    env = dict(os.environ)
    env["DE_AGENT_PROJECT_DIR"] = str(project_dir)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30,
    )
    return proc


def events(project_dir):
    p = project_dir / "work" / ".escalations" / "events.jsonl"
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def test_malformed_input_exits_zero(tmp_path):
    proc = run_hook_raw("not json", tmp_path)
    assert proc.returncode == 0


def run_hook_raw(raw, project_dir):
    env = dict(os.environ)
    env["DE_AGENT_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=raw, capture_output=True, text=True, env=env, timeout=30
    )


def test_pretooluse_allows_fresh_call(tmp_path):
    proc = run_hook(
        {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}},
        tmp_path,
    )
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_repeated_attempts_escalate_with_valid_timestamp(tmp_path):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "kubectl get pods"},
        "tool_output": "ok",
    }
    # MAX_REPEATED_ATTEMPTS defaults to 3
    for _ in range(3):
        run_hook(payload, tmp_path)
    evs = events(tmp_path)
    assert evs, "expected an escalation event after repeated identical calls"
    ts = evs[-1]["ts"]
    # Well-formed ISO-8601: a single trailing Z, never a "+00:00Z" hybrid.
    assert ts.endswith("Z") and "+00:00" not in ts
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts)


def test_structured_tool_output_does_not_crash(tmp_path):
    # tool_response as a dict must not crash the breaker (was AttributeError on .lower()).
    proc = run_hook(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "SomeStructuredTool",
            "tool_input": {"x": 1},
            "tool_response": {"status": "error", "detail": "policy blocked"},
            "is_error": True,
        },
        tmp_path,
    )
    assert proc.returncode == 0
    assert "Traceback" not in proc.stderr


def test_pretooluse_denies_already_escalated_call(tmp_path):
    # Drive a PostToolUse escalation first, then the same call at PreToolUse denies.
    call = {"tool_name": "Bash", "tool_input": {"command": "repeat me"}}
    for _ in range(3):
        run_hook({**call, "hook_event_name": "PostToolUse", "tool_output": "ok"}, tmp_path)
    proc = run_hook({**call, "hook_event_name": "PreToolUse"}, tmp_path)
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
