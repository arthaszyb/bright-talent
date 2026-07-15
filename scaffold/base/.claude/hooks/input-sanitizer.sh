#!/usr/bin/env python3
"""
input-sanitizer.sh — UserPromptSubmit hook
Blocks control characters (0x00–0x08, 0x0B–0x0C, 0x0E–0x1F) and strips invisible Unicode.
Resolves DE_AGENT_PROJECT_DIR (or falls back to CLAUDE_PROJECT_DIR, then cwd).
"""

import sys
import json
import os

# Resolve project directory
project_dir = os.getenv('DE_AGENT_PROJECT_DIR') or os.getenv('CLAUDE_PROJECT_DIR') or '.'

try:
    json_input = json.load(sys.stdin)
    prompt = json_input.get('prompt', '')
except (json.JSONDecodeError, ValueError):
    # If JSON parsing fails, treat entire stdin as the prompt
    prompt = sys.stdin.read()

if not prompt:
    # Empty prompt — pass through
    sys.exit(0)

# Check for control characters: 0x00–0x08, 0x0B–0x0C, 0x0E–0x1F
for char in prompt:
    code = ord(char)
    if (0x00 <= code <= 0x08) or (0x0B <= code <= 0x0C) or (0x0E <= code <= 0x1F):
        # Found a control character — block
        print(json.dumps({
            "decision": "block",
            "reason": "Input contains suspicious control characters"
        }))
        sys.exit(2)

# Strip invisible Unicode codepoints:
# U+200B–U+200F (zero-width), U+2028–U+2029 (line/paragraph sep), U+2060–U+206F (invisible operators), U+FEFF (BOM)
invisible_ranges = [
    (0x200B, 0x200F),  # Zero-width space, joiner, etc.
    (0x2028, 0x2029),  # Line/paragraph separators
    (0x2060, 0x206F),  # Invisible operators, word joiner, etc.
    (0xFEFF, 0xFEFF),  # BOM
]

sanitized = ''
changed = False
for char in prompt:
    code = ord(char)
    is_invisible = any(start <= code <= end for start, end in invisible_ranges)
    if is_invisible:
        changed = True
    else:
        sanitized += char

if changed:
    # Emit additionalContext with the sanitized prompt
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"The user input was automatically sanitized to remove invisible Unicode characters and formatting markers. The sanitized version below is authoritative:\n\n{sanitized}"
        }
    }
    print(json.dumps(output))

sys.exit(0)
