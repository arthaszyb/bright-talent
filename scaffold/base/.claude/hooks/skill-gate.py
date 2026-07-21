#!/usr/bin/env python3
"""
skill-gate.py — PreToolUse hook
Enforces the CLAUDE.md three-step protocol: confirm need → select skill → execute tool.
No tool calls before Skill has been invoked this session (except allowlist).
"""

import json
import os
import sys

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

try:
    hook_input = json.load(sys.stdin)
    tool_name = hook_input.get('tool_name', '')
    session_id = hook_input.get('session_id', '')
except (json.JSONDecodeError, ValueError, EOFError):
    # Malformed input — allow (don't break)
    sys.exit(0)

if not tool_name or not session_id:
    sys.exit(0)

# Construct flag file path
if project_dir and project_dir != '.':
    flag_dir = os.path.join(project_dir, 'work', '.skill-gate')
else:
    flag_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'work', '.skill-gate')

flag_file = os.path.join(flag_dir, f'{session_id}.flag')

# Special case: If Skill tool is called, create the flag file and allow
if tool_name == 'Skill':
    try:
        os.makedirs(flag_dir, exist_ok=True)
        with open(flag_file, 'w') as f:
            f.write('')  # Just touch the file
    except Exception:
        pass  # If we can't write, still allow
    sys.exit(0)

# Check allowlist (for other allowed tools)
if tool_name in ALWAYS_ALLOW:
    sys.exit(0)

# For other tools, check if flag exists
if os.path.exists(flag_file):
    # Skill has been called — allow
    sys.exit(0)

# Tool not in allowlist and flag doesn't exist — deny
output = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "Tool use is gated by the CLAUDE.md three-step protocol. "
            "Step 1: Confirm you need this tool for the task. "
            "Step 2: Select the appropriate skill using /Skill. "
            "Step 3: Then execute the tool.\n"
            "If no local skill matches your need, escalate immediately with the 'capability gap' category."
        )
    }
}
print(json.dumps(output))
sys.exit(0)
