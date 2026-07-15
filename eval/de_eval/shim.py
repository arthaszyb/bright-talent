"""PATH-shim generation (eval-spec.md §5.4 step 1-2).

One executable shim per distinct first word of every fixture's
`command_prefix` in the case, plus a fixed deny-set (`curl wget ssh
kubectl`) so a stray real call can never escape during replay. Every shim
runs the same small script; it reconstructs `basename(argv[0]) + " " +
" ".join(argv[1:])`, ships that string to the fixture server over the unix
socket named by `DE_EVAL_FIXTURE_SOCK`, and replays the response.
"""

from __future__ import annotations

import stat
from pathlib import Path

from de_eval.paths import DENY_SET_COMMANDS

SHIM_BODY = '''#!/usr/bin/env python3
"""de-eval PATH shim -- see eval/de_eval/shim.py for the generator.

Reconstructs the invoked command, ships it to the fixture server over the
unix socket named by DE_EVAL_FIXTURE_SOCK, and replays the response
(stdout/stderr/exit_code). Exits 97 on any unmatched command or if the
socket is unreachable -- the case fails closed, per eval-spec.md 5.3/5.4.
"""
import json
import os
import socket
import sys

UNMATCHED_MARKER = "de-eval: unmatched command (no fixture configured, no fallback)"


def main() -> int:
    sock_path = os.environ.get("DE_EVAL_FIXTURE_SOCK")
    argv0 = os.path.basename(sys.argv[0])
    command = " ".join([argv0] + sys.argv[1:])

    if not sock_path:
        sys.stderr.write("de-eval shim: DE_EVAL_FIXTURE_SOCK not set\\n")
        return 97

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(sock_path)
        s.sendall(json.dumps({"command": command}).encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        s.close()
        data = b"".join(chunks)
    except OSError as e:
        sys.stderr.write(f"de-eval shim: cannot reach fixture server: {e}\\n")
        return 97

    try:
        resp = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        sys.stderr.write(f"de-eval shim: malformed fixture server response: {e}\\n")
        return 97

    if not resp.get("matched", False):
        sys.stderr.write(UNMATCHED_MARKER + f": {command}\\n")
        return 97

    sys.stdout.write(resp.get("stdout", ""))
    sys.stderr.write(resp.get("stderr", ""))
    try:
        return int(resp.get("exit_code", 1))
    except (TypeError, ValueError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def first_words(fixtures: list[dict]) -> set[str]:
    words: set[str] = set()
    for fx in fixtures:
        prefix = (fx.get("command_prefix") or "").strip()
        if not prefix:
            continue
        words.add(prefix.split()[0])
    return words


def shim_names_for_case(fixtures: list[dict]) -> set[str]:
    return first_words(fixtures) | set(DENY_SET_COMMANDS)


def write_shims(shim_dir: Path, names: set[str]) -> list[Path]:
    shim_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in sorted(names):
        path = shim_dir / name
        path.write_text(SHIM_BODY, encoding="utf-8")
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(path)
    return written
