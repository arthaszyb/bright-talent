#!/usr/bin/env python3
"""Fake `claude` CLI shim for offline bridge tests.

Emulates just enough of the `claude --output-format stream-json
--input-format stream-json --verbose --permission-mode <mode>` protocol for
bridge/bridge/sessions.py to exercise its reader loop end to end, with no
real Claude Code binary or network access involved.

Usage (as agent.claude_cmd in test configs):
    "python3 /path/to/fake_claude.py"

Behavior:
- Reads argv for --resume <id>; if present, reuses that session_id, else
  generates a fresh one.
- Reads stdin line by line. For each {"type": "user", ...} frame, emits:
  1. a `system` init frame carrying session_id (first turn only)
  2. an `assistant` frame echoing "echo: <content>"
  3. a `result` frame with the same text as the authoritative reply
- Keeps looping (does not exit) until stdin is closed (EOF), then exits 0.
"""
from __future__ import annotations

import json
import sys
import uuid


def main() -> int:
    argv = sys.argv[1:]
    session_id = None
    if "--resume" in argv:
        idx = argv.index("--resume")
        if idx + 1 < len(argv):
            session_id = argv[idx + 1]
    if not session_id:
        session_id = uuid.uuid4().hex

    sent_init = False

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "user":
            continue

        content = (obj.get("message") or {}).get("content", "")
        reply = f"echo: {content}"

        if not sent_init:
            _emit({"type": "system", "subtype": "init", "session_id": session_id})
            sent_init = True

        _emit(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": reply}]},
                "session_id": session_id,
            }
        )
        _emit(
            {
                "type": "result",
                "session_id": session_id,
                "result": reply,
                "is_error": False,
            }
        )

    return 0


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
