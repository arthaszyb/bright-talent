"""Behavioral tests for the result-sanitizer PostToolUse hook.

Driven as a subprocess with hook JSON on stdin, exactly as the agent harness
runs it. The headline property: credential scanning must survive structured
(non-string) tool output — PostToolUse `tool_response` is usually a dict/list,
and a naive re.search over it would crash and silently defeat the scan.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "base" / ".claude" / "hooks" / "result-sanitizer.sh"

# Built at runtime from split parts so the literal never appears in source.
_GH_TOKEN = "ghp_" + "A" * 36
_AWS_KEY = "AKIA" + "B" * 16


def run_hook(payload):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
    )


def flagged(proc) -> bool:
    return proc.returncode == 0 and "SECURITY NOTICE" in proc.stdout


def test_string_output_with_credential_is_flagged():
    proc = run_hook({"tool_output": f"token={_GH_TOKEN}"})
    assert flagged(proc)


def test_structured_dict_output_with_credential_is_flagged():
    # The regression: a dict tool_response used to crash re.search (TypeError).
    proc = run_hook({"tool_response": {"stdout": f"export TOKEN={_GH_TOKEN}"}})
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr
    assert flagged(proc)


def test_nested_list_output_with_credential_is_flagged():
    proc = run_hook({"result": ["line", {"aws": _AWS_KEY}]})
    assert flagged(proc)


def test_clean_structured_output_is_silent():
    proc = run_hook({"tool_response": {"stdout": "nothing secret here"}})
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_empty_output_passes_through():
    proc = run_hook({"tool_response": ""})
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_malformed_input_does_not_crash():
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json", capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
