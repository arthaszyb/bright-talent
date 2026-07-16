#!/usr/bin/env python3
"""Mock chat-platform client for driving the de-demo bridge (fictional Acme Corp universe).

Stdlib-only. Simulates a chat platform webhook sender: it signs and POSTs
`message`/`verification` events to the bridge's `/webhook/events` endpoint,
and also runs a tiny local HTTP server that receives the bridge's outbound
reply POSTs (the bridge's `chat.api_base_url` should point at this server).

NOTE: port 8801 belongs to the unrelated mock Change Gateway service
(mocks/change_gateway.py) and is never used by this script - don't confuse
the two. This script talks to the bridge on port 9100 (default) and listens
for replies on port 9101 (default).

Reply delivery contract (must match bridge/bridge/app.py's deliver_reply):
the bridge POSTs JSON {"channel_id", "thread_id", "text"} to whatever URL is
configured as chat.api_base_url. This client accepts that POST on `/`
(any path is accepted) on its callback listener.

Usage:
  One-shot message:
    python3 mocks/chat_client.py --bridge-url http://localhost:9100 \\
        --secret changeme-demo-secret --channel c1 --thread t1 --sender u1 \\
        --message "hello"

  Verification handshake:
    python3 mocks/chat_client.py --bridge-url http://localhost:9100 \\
        --secret changeme-demo-secret --verify

  REPL (interactive, reads lines from stdin):
    python3 mocks/chat_client.py --bridge-url http://localhost:9100 \\
        --secret changeme-demo-secret --channel c1 --thread t1 --sender u1
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import queue
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPLY_QUEUE: "queue.Queue[str]" = queue.Queue()


def sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReplyCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: A002 - silence default access logs
        pass

    def do_POST(self):  # noqa: N802 - http.server naming convention
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        text = payload.get("text", "")
        print(f"[reply] {text}", flush=True)
        REPLY_QUEUE.put(text)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')


def start_callback_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), ReplyCallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def post_event(bridge_url: str, secret: str, event: dict) -> tuple[int, bytes]:
    raw_body = json.dumps(event).encode("utf-8")
    signature = sign(secret, raw_body)
    req = Request(
        f"{bridge_url.rstrip('/')}/webhook/events",
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Chat-Signature": signature,
        },
    )
    try:
        with urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except HTTPError as e:
        return e.code, e.read()
    except URLError as e:
        print(f"error: could not reach bridge at {bridge_url}: {e}", file=sys.stderr)
        return 0, b""


def build_message_event(channel_id: str, thread_id: str, sender_id: str, text: str) -> dict:
    return {
        "event_type": "message",
        "event_id": f"evt-{uuid.uuid4().hex}",
        "channel_id": channel_id,
        "thread_id": thread_id,
        "sender": {"user_id": sender_id, "email": f"{sender_id}@acme.example"},
        "text": text,
        "ts": now_iso(),
    }


def wait_for_reply(timeout: float = 15.0) -> str | None:
    try:
        return REPLY_QUEUE.get(timeout=timeout)
    except queue.Empty:
        return None


def run_one_shot(args: argparse.Namespace) -> int:
    start_callback_server(args.callback_port)
    event = build_message_event(args.channel, args.thread, args.sender, args.message)
    status, body = post_event(args.bridge_url, args.secret, event)
    if status != 200:
        print(f"error: webhook POST returned status {status}: {body!r}", file=sys.stderr)
        return 1

    reply = wait_for_reply(timeout=15.0)
    if reply is None:
        print("(no reply received within 15s)")
        return 0
    return 0


def run_verify(args: argparse.Namespace) -> int:
    challenge = f"chal-{uuid.uuid4().hex}"
    event = {"event_type": "verification", "challenge": challenge}
    status, body = post_event(args.bridge_url, args.secret, event)
    print(f"status={status} body={body.decode('utf-8', errors='replace')}")
    if status != 200:
        return 1
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        print("error: verification response was not valid JSON")
        return 1
    if parsed.get("challenge") != challenge:
        print("error: challenge echoed back did not match")
        return 1
    print("verification ok: challenge echoed correctly")
    return 0


def run_repl(args: argparse.Namespace) -> int:
    start_callback_server(args.callback_port)
    print(
        f"REPL mode: channel={args.channel} thread={args.thread} sender={args.sender}. "
        "Type a message and press enter; Ctrl-D/exit/quit to stop."
    )
    try:
        for line in sys.stdin:
            text = line.strip()
            if not text:
                continue
            if text in ("exit", "quit"):
                break
            event = build_message_event(args.channel, args.thread, args.sender, text)
            status, body = post_event(args.bridge_url, args.secret, event)
            if status != 200:
                print(f"error: webhook POST returned status {status}: {body!r}", file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bridge-url", default="http://localhost:9100")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--channel", default="c1")
    parser.add_argument("--thread", default="t1")
    parser.add_argument("--sender", default="u1")
    parser.add_argument("--callback-port", type=int, default=9101)
    parser.add_argument(
        "--reply-mode",
        default="sync",
        choices=["sync"],
        help="reserved for future modes; currently only 'sync' one-shot/REPL delivery is implemented",
    )
    parser.add_argument("--message", default=None, help="send one message and exit (one-shot mode)")
    parser.add_argument("--verify", action="store_true", help="send a verification challenge and exit")
    args = parser.parse_args()

    if args.verify:
        return run_verify(args)
    if args.message is not None:
        return run_one_shot(args)
    return run_repl(args)


if __name__ == "__main__":
    sys.exit(main())
