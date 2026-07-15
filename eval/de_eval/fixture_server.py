"""Unix-socket fixture server for PATH-shim command replay (eval-spec.md §5.4 step 3).

Matches the reconstructed command string against `fixtures[].command_prefix`
entries first-match-in-file-order (§5.3): a literal-prefix match serves that
fixture's {stdout, stderr, exit_code}; a `command_prefix: ""` fallback (only
valid as the last fixture) is served but recorded `"fallback": true`; no
match at all is an unmatched-command verdict (the shim then exits 97).
Every request -- matched, fallback, or unmatched -- is appended to
`.commands.jsonl`.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FixtureFileError(Exception):
    """Malformed *.mock.yaml fixtures list (authoring error, not a case failure)."""


def validate_fixtures(fixtures: list[dict[str, Any]]) -> None:
    seen_fallback = False
    for fx in fixtures:
        if seen_fallback:
            raise FixtureFileError(
                "fixture file error: an entry follows a command_prefix: '' fallback "
                "(unreachable fixture)"
            )
        if (fx.get("command_prefix") or "") == "":
            seen_fallback = True


def match_fixture(fixtures: list[dict[str, Any]], command: str) -> tuple[dict[str, Any] | None, bool]:
    """Returns (fixture, is_fallback). fixture is None on no match."""
    for fx in fixtures:
        prefix = fx.get("command_prefix") or ""
        if prefix == "":
            return fx, True
        if command.startswith(prefix):
            return fx, False
    return None, False


class FixtureServer:
    def __init__(self, fixtures: list[dict[str, Any]], commands_jsonl_path: Path, sock_path: Path):
        validate_fixtures(fixtures)
        self.fixtures = fixtures
        self.commands_jsonl_path = commands_jsonl_path
        self.sock_path = sock_path
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.commands_jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self.sock_path.exists():
            self.sock_path.unlink()
        self.sock_path.parent.mkdir(parents=True, exist_ok=True)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.sock_path))
        self._sock.listen(32)
        self._sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self.sock_path.exists():
            try:
                self.sock_path.unlink()
            except OSError:
                pass

    def _serve_forever(self) -> None:
        assert self._sock is not None
        while not self._stop_event.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(10)
            chunks = []
            try:
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except OSError:
                pass
            data = b"".join(chunks)
            try:
                req = json.loads(data.decode("utf-8"))
                command = str(req.get("command", ""))
            except (UnicodeDecodeError, json.JSONDecodeError):
                conn.sendall(json.dumps({"matched": False}).encode("utf-8"))
                return

            fx, fallback = match_fixture(self.fixtures, command)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            if fx is None:
                self._append(
                    {
                        "ts": ts,
                        "command": command,
                        "fixture": None,
                        "fallback": False,
                        "exit_code": 97,
                        "matched": False,
                    }
                )
                conn.sendall(json.dumps({"matched": False}).encode("utf-8"))
                return

            exit_code = int(fx.get("exit_code", 0))
            self._append(
                {
                    "ts": ts,
                    "command": command,
                    "fixture": fx.get("step"),
                    "fallback": fallback,
                    "exit_code": exit_code,
                    "matched": True,
                }
            )
            conn.sendall(
                json.dumps(
                    {
                        "matched": True,
                        "stdout": fx.get("stdout", ""),
                        "stderr": fx.get("stderr", ""),
                        "exit_code": exit_code,
                    }
                ).encode("utf-8")
            )

    def _append(self, record: dict[str, Any]) -> None:
        with self._lock:
            with open(self.commands_jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")


def _main() -> int:  # pragma: no cover - manual/debug entrypoint
    """Standalone runner for manual shim proofs:
    python -m de_eval.fixture_server <case.mock.yaml> <sock_path> [commands_jsonl_path]

    Runs in the foreground until Ctrl-C. Export
    DE_EVAL_FIXTURE_SOCK=<sock_path> before invoking a generated shim by hand.
    """
    import argparse
    import time

    import yaml

    parser = argparse.ArgumentParser()
    parser.add_argument("mock_yaml")
    parser.add_argument("sock_path")
    parser.add_argument("commands_jsonl", nargs="?", default=".commands.jsonl")
    args = parser.parse_args()

    with open(args.mock_yaml, "r", encoding="utf-8") as f:
        case = yaml.safe_load(f)
    fixtures = case.get("fixtures") or []

    server = FixtureServer(fixtures, Path(args.commands_jsonl), Path(args.sock_path))
    server.start()
    print(f"de-eval fixture server listening on {args.sock_path}", file=sys.stderr)
    print(f"commands.jsonl -> {args.commands_jsonl}", file=sys.stderr)
    print("export DE_EVAL_FIXTURE_SOCK=" + str(Path(args.sock_path).resolve()), file=sys.stderr)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
