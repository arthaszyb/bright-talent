#!/usr/bin/env python3
"""
skill-gate.py — PreToolUse hook
Enforces the CLAUDE.md three-step protocol: confirm need → select skill → execute tool.
No tool calls before Skill has been invoked this session (except allowlist).

Fail-closed: malformed hook input or missing identifying fields is denied,
not waved through. The gate also expires — a Skill invocation opens a
time-boxed window (DE_SKILL_GATE_TTL_SECONDS, default 900s, refreshed by
each Skill call); after it lapses the agent must re-invoke Skill.
"""

import json
import os
import sys
import time

# Resolve project directory
project_dir = os.getenv('DE_AGENT_PROJECT_DIR') or os.getenv('CLAUDE_PROJECT_DIR') or '.'

# Always-allow set
ALWAYS_ALLOW = {
    'Skill',
    'Read',
    'Grep',
    'Glob',
    'mcp__de-agent-escalate__escalate'
}

GATE_TTL_SECONDS = int(os.getenv('DE_SKILL_GATE_TTL_SECONDS', '900'))

PROTOCOL_REMINDER = (
    "Tool use is gated by the CLAUDE.md three-step protocol. "
    "Step 1: Confirm you need this tool for the task. "
    "Step 2: Select the appropriate skill using /Skill. "
    "Step 3: Then execute the tool.\n"
    "If no local skill matches your need, escalate immediately with the 'capability gap' category."
)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


try:
    hook_input = json.load(sys.stdin)
    tool_name = hook_input.get('tool_name', '')
    session_id = hook_input.get('session_id', '')
except (json.JSONDecodeError, ValueError, EOFError):
    deny("skill-gate: malformed hook input — failing closed. Retry the call through the normal tool protocol.")

if not tool_name or not session_id:
    deny("skill-gate: hook input missing tool_name/session_id — failing closed.")

# Construct flag file path
if project_dir and project_dir != '.':
    flag_dir = os.path.join(project_dir, 'work', '.skill-gate')
else:
    flag_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'work', '.skill-gate')

flag_file = os.path.join(flag_dir, f'{session_id}.flag')

# Special case: If Skill tool is called, open/refresh the gate window and allow
if tool_name == 'Skill':
    try:
        os.makedirs(flag_dir, exist_ok=True)
        with open(flag_file, 'w') as f:
            f.write('')  # mtime is the window start
    except Exception as e:
        # The Skill call itself may proceed, but the window could not be
        # recorded — subsequent gated tools will be denied, so say so.
        sys.stderr.write(f"skill-gate: could not record gate window: {e}\n")
    sys.exit(0)

# Check allowlist (for other allowed tools)
if tool_name in ALWAYS_ALLOW:
    sys.exit(0)

# For other tools, the gate window must be open and fresh
if os.path.exists(flag_file):
    try:
        age = time.time() - os.path.getmtime(flag_file)
    except OSError:
        deny("skill-gate: cannot read gate window state — failing closed. Re-invoke the skill.")
    if age <= GATE_TTL_SECONDS:
        sys.exit(0)
    deny(
        f"skill-gate: the skill window opened {int(age)}s ago and expired "
        f"(TTL {GATE_TTL_SECONDS}s). Re-invoke the appropriate skill via /Skill "
        "to confirm the tool contract, then retry."
    )

deny(PROTOCOL_REMINDER)
