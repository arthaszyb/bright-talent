from __future__ import annotations

import json
import time
from pathlib import Path

from conftest import TEST_SECRET, sign


def post_event(client, event: dict):
    body = json.dumps(event).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Chat-Signature": sign(TEST_SECRET, body),
    }
    return client.post("/webhook/events", content=body, headers=headers)


def read_sessions_file(config) -> dict:
    p = Path(config.sessions.data_dir) / "sessions.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def wait_for_key(config, key: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = read_sessions_file(config)
        entry = data.get("sessions", {}).get(key)
        if entry:
            return entry
        time.sleep(0.05)
    return {}


def message_event(event_id, channel_id, thread_id, sender_id, text):
    return {
        "event_type": "message",
        "event_id": event_id,
        "channel_id": channel_id,
        "thread_id": thread_id,
        "sender": {"user_id": sender_id, "email": f"{sender_id}@acme.example"},
        "text": text,
        "ts": "2026-01-01T00:00:00Z",
    }


def test_session_reuse_single_subprocess(client):
    config = client.bridge_config
    key = "c-reuse:t-reuse"

    resp1 = post_event(client, message_event("evt-1", "c-reuse", "t-reuse", "u1", "hello one"))
    assert resp1.status_code == 200
    entry1 = wait_for_key(config, key)
    assert entry1, "expected sessions.json entry after first message"
    assert entry1["session_id"]

    created_at_1 = entry1["created_at"]

    resp2 = post_event(client, message_event("evt-2", "c-reuse", "t-reuse", "u1", "hello two"))
    assert resp2.status_code == 200
    entry2 = wait_for_key(config, key)

    assert entry2["created_at"] == created_at_1, "created_at must stay stable across reused session"
    assert entry2["session_id"] == entry1["session_id"]

    data = read_sessions_file(config)
    assert data["schema_version"] == 4


def test_session_isolation_across_threads(client):
    config = client.bridge_config

    post_event(client, message_event("evt-3", "c-iso", "t-a", "u1", "message a"))
    post_event(client, message_event("evt-4", "c-iso", "t-b", "u1", "message b"))

    entry_a = wait_for_key(config, "c-iso:t-a")
    entry_b = wait_for_key(config, "c-iso:t-b")

    assert entry_a and entry_b
    assert entry_a["session_id"]
    assert entry_b["session_id"]
    assert entry_a["session_id"] != entry_b["session_id"]


def test_allowlist_blocks_disallowed_sender(bridge_app_factory):
    from fastapi.testclient import TestClient

    app, config = bridge_app_factory(auth={"allowed_users": ["u-ok"], "admin_users": []})
    with TestClient(app) as client:
        resp = post_event(
            client, message_event("evt-5", "c-auth", "t-auth", "u-blocked", "should be dropped")
        )
        assert resp.status_code == 200

        time.sleep(0.3)
        data = read_sessions_file(config)
        assert "c-auth:t-auth" not in data.get("sessions", {})


def test_reset_clears_session_entry(client):
    config = client.bridge_config
    key = "c-reset:t-reset"

    post_event(client, message_event("evt-6", "c-reset", "t-reset", "u1", "hello"))
    entry = wait_for_key(config, key)
    assert entry

    resp = post_event(client, message_event("evt-7", "c-reset", "t-reset", "u1", "/reset"))
    assert resp.status_code == 200

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        data = read_sessions_file(config)
        if key not in data.get("sessions", {}):
            break
        time.sleep(0.05)

    data = read_sessions_file(config)
    assert key not in data.get("sessions", {})
