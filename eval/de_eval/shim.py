"""PATH-shim generation (eval-spec.md §5.4 step 1-2).

One executable shim per distinct first word of every fixture's
`command_prefix` in the case, plus a fixed deny-set (`curl wget ssh
kubectl`). Every shim runs the same small script; it reconstructs
`basename(argv[0]) + " " + " ".join(argv[1:])`, ships that string to the
fixture server over the unix socket named by `DE_EVAL_FIXTURE_SOCK`, and
replays the response.

Scope of the guarantee (be precise, this is a security property): the shim
directory is *prepended* to `PATH`, so interception covers exactly the
commands that have a shim — the fixtures' own first words plus the
deny-set. A command with no shim resolves to the real binary further down
`PATH` and executes for real; the deny-set exists to cover the dangerous
cases fixtures would not otherwise name. Invocations by path
(`/usr/bin/git`, `./tool`) bypass `PATH` lookup entirely and therefore
cannot be shimmed at all, which is why such a `command_prefix` is rejected
as an authoring error rather than silently accepted.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from de_eval.fixture_server import FixtureFileError
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
        word = prefix.split()[0]
        if "/" in word or os.sep in word:
            # Two reasons to refuse. A path invocation skips PATH lookup, so
            # no shim could ever intercept it — accepting the fixture would
            # promise isolation that does not exist. And `shim_dir / word`
            # with an absolute word silently discards shim_dir (pathlib), so
            # write_shims would write over the real binary's path instead.
            raise FixtureFileError(
                "fixture file error: command_prefix must start with a bare command name, "
                f"got {word!r} — a command invoked by path bypasses PATH lookup and cannot "
                "be shimmed, so strict replay could not intercept it"
            )
        words.add(word)
    return words


def shim_names_for_case(fixtures: list[dict]) -> set[str]:
    return first_words(fixtures) | set(DENY_SET_COMMANDS)


def write_shims(shim_dir: Path, names: set[str]) -> list[Path]:
    shim_dir.mkdir(parents=True, exist_ok=True)
    resolved_root = shim_dir.resolve()
    written: list[Path] = []
    for name in sorted(names):
        path = shim_dir / name
        # Defense in depth: first_words() already rejects path-bearing names,
        # but never write a shim outside the shim directory — an absolute
        # name would otherwise land on the real binary's path.
        if path.resolve().parent != resolved_root:
            raise FixtureFileError(
                f"fixture file error: shim name {name!r} would write outside the shim directory"
            )
        path.write_text(SHIM_BODY, encoding="utf-8")
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(path)
    return written
