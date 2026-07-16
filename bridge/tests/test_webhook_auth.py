from __future__ import annotations

import json

from conftest import TEST_SECRET, sign


def post_event(client, event: dict, secret: str = TEST_SECRET, with_signature: bool = True):
    body = json.dumps(event).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if with_signature:
        headers["X-Chat-Signature"] = sign(secret, body)
    return client.post("/webhook/events", content=body, headers=headers)


def test_valid_signature_returns_200(client):
    event = {
        "event_type": "message",
        "event_id": "evt-1",
        "channel_id": "c1",
        "thread_id": "t1",
        "sender": {"user_id": "u1", "email": "u1@acme.example"},
        "text": "hello",
        "ts": "2026-01-01T00:00:00Z",
    }
    resp = post_event(client, event)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_bad_signature_returns_401(client):
    event = {
        "event_type": "message",
        "event_id": "evt-2",
        "channel_id": "c1",
        "thread_id": "t1",
        "sender": {"user_id": "u1"},
        "text": "hello",
        "ts": "2026-01-01T00:00:00Z",
    }
    resp = post_event(client, event, secret="wrong-secret")
    assert resp.status_code == 401


def test_missing_signature_header_returns_401(client):
    event = {
        "event_type": "message",
        "event_id": "evt-3",
        "channel_id": "c1",
        "thread_id": "t1",
        "sender": {"user_id": "u1"},
        "text": "hello",
        "ts": "2026-01-01T00:00:00Z",
    }
    resp = post_event(client, event, with_signature=False)
    assert resp.status_code == 401


def test_bad_signature_creates_no_session(client, tmp_path):
    event = {
        "event_type": "message",
        "event_id": "evt-4",
        "channel_id": "c-bad",
        "thread_id": "t-bad",
        "sender": {"user_id": "u1"},
        "text": "hello",
        "ts": "2026-01-01T00:00:00Z",
    }
    post_event(client, event, secret="wrong-secret")
    sessions_path = client.bridge_config.sessions.data_dir
    from pathlib import Path

    p = Path(sessions_path) / "sessions.json"
    if p.exists():
        data = json.loads(p.read_text())
        assert "c-bad:t-bad" not in data.get("sessions", {})
    else:
        assert True
