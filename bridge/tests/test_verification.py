from __future__ import annotations

import json

from conftest import TEST_SECRET, sign


def test_verification_challenge_echoed(client):
    event = {"event_type": "verification", "challenge": "opaque-challenge-123"}
    body = json.dumps(event).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Chat-Signature": sign(TEST_SECRET, body),
    }
    resp = client.post("/webhook/events", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "opaque-challenge-123"}


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
