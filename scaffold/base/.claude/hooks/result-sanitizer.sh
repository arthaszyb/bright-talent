#!/usr/bin/env python3
"""
result-sanitizer.sh — PostToolUse hook
Scans tool output for credential patterns and warns (cannot rewrite; tool already ran).
"""

import sys
import json
import os
import re

# Resolve project directory
project_dir = os.getenv('DE_AGENT_PROJECT_DIR') or os.getenv('CLAUDE_PROJECT_DIR') or '.'

try:
    hook_input = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError, EOFError):
    sys.exit(0)

# Extract tool output from various possible keys
tool_output = (
    hook_input.get('tool_output') or
    hook_input.get('tool_response') or
    hook_input.get('tool_result') or
    hook_input.get('result') or
    hook_input.get('stderr') or
    hook_input.get('stdout') or
    ""
)

if not tool_output:
    sys.exit(0)

# PostToolUse tool output is frequently structured (a dict/list — e.g. a
# command result or a parsed API response), not a bare string. re.search on a
# non-string raises TypeError, which would crash the hook and silently defeat
# credential scanning for exactly the outputs most likely to embed secrets.
# Coerce to text (JSON-serialize structured values) so nested credential
# values are still scanned.
if not isinstance(tool_output, str):
    try:
        tool_output = json.dumps(tool_output, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        tool_output = str(tool_output)

# Credential patterns (split to avoid literal pattern matches in source)
patterns = [
    r'sk-ant-' + r'[A-Za-z0-9_-]{20,}',
    r'sk-' + r'[A-Za-z0-9]{20,}',
    r'ghp_' + r'[A-Za-z0-9]{36}',
    r'glpat-' + r'[A-Za-z0-9_-]{20,}',
    r'AKIA' + r'[0-9A-Z]{16}',
    r'(password|secret|token)\s*[:=]\s*\S+',
]

# Check if any pattern matches
found_credential = False
for pattern in patterns:
    if re.search(pattern, tool_output, re.IGNORECASE):
        found_credential = True
        break

if found_credential:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "SECURITY NOTICE: The tool output above likely contains sensitive credentials. "
                "Do NOT repeat, echo, log, forward, or base any decisions on these credential values. "
                "Treat them as already redacted. "
                "If this was unintended, ensure secrets are never output by tools."
            )
        }
    }
    print(json.dumps(output))

sys.exit(0)
