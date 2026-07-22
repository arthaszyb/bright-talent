"""Behavioral tests for the skill-gate PreToolUse hook.

The hook is a standalone stdlib script (scaffold/base/.claude/hooks/
skill-gate.py) executed by the agent harness with hook JSON on stdin; these
tests drive it the same way. Gate semantics under test: fail-closed on bad
input, allowlist, Skill opens a time-boxed window, window expiry re-denies.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "base" / ".claude" / "hooks" / "skill-gate.py"


def run_hook(stdin_text: str, project_dir: Path, ttl: int | None = None):
    env = dict(os.environ)
    env["DE_AGENT_PROJECT_DIR"] = str(project_dir)
    if ttl is not None:
        env["DE_SKILL_GATE_TTL_SECONDS"] = str(ttl)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text, capture_output=True, text=True, env=env, timeout=30,
    )
    decision = None
    if proc.stdout.strip():
        payload = json.loads(proc.stdout)
        decision = payload["hookSpecificOutput"]["permissionDecision"]
    return proc.returncode, decision, proc.stdout


def event(tool_name: str, session_id: str = "sess-1") -> str:
    return json.dumps({"tool_name": tool_name, "session_id": session_id})


def test_malformed_input_is_denied(tmp_path):
    rc, decision, _ = run_hook("this is not json", tmp_path)
    assert rc == 0 and decision == "deny"


def test_missing_fields_are_denied(tmp_path):
    rc, decision, _ = run_hook(json.dumps({"tool_name": "Bash"}), tmp_path)
    assert rc == 0 and decision == "deny"


def test_gated_tool_denied_before_any_skill(tmp_path):
    rc, decision, _ = run_hook(event("Bash"), tmp_path)
    assert rc == 0 and decision == "deny"


def test_allowlisted_tools_pass_without_skill(tmp_path):
    for tool in ("Read", "Grep", "Glob", "mcp__de-agent-escalate__escalate"):
        rc, decision, _ = run_hook(event(tool), tmp_path)
        assert rc == 0 and decision is None, tool


def test_skill_call_opens_the_window(tmp_path):
    rc, decision, _ = run_hook(event("Skill"), tmp_path)
    assert rc == 0 and decision is None
    assert (tmp_path / "work" / ".skill-gate" / "sess-1.flag").is_file()
    rc, decision, _ = run_hook(event("Bash"), tmp_path)
    assert rc == 0 and decision is None


def test_window_is_per_session(tmp_path):
    run_hook(event("Skill", session_id="sess-a"), tmp_path)
    rc, decision, _ = run_hook(event("Bash", session_id="sess-b"), tmp_path)
    assert decision == "deny"


def test_expired_window_is_denied_and_mentions_reinvoke(tmp_path):
    run_hook(event("Skill"), tmp_path)
    flag = tmp_path / "work" / ".skill-gate" / "sess-1.flag"
    stale = time.time() - 120
    os.utime(flag, (stale, stale))
    rc, decision, out = run_hook(event("Bash"), tmp_path, ttl=60)
    assert decision == "deny"
    assert "expired" in out


def test_skill_reinvocation_refreshes_expired_window(tmp_path):
    run_hook(event("Skill"), tmp_path)
    flag = tmp_path / "work" / ".skill-gate" / "sess-1.flag"
    stale = time.time() - 120
    os.utime(flag, (stale, stale))
    run_hook(event("Skill"), tmp_path, ttl=60)
    rc, decision, _ = run_hook(event("Bash"), tmp_path, ttl=60)
    assert rc == 0 and decision is None
