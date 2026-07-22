"""Tests for the mock Change Gateway — the EXECUTION layer's only write path.

Boots the real ThreadingHTTPServer on an ephemeral port and exercises it
over HTTP exactly as the skill scripts do (stdlib urllib, JSON bodies).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "change_gateway.py"
_spec = importlib.util.spec_from_file_location("change_gateway", _MODULE_PATH)
change_gateway = importlib.util.module_from_spec(_spec)
sys.modules["change_gateway"] = change_gateway
_spec.loader.exec_module(change_gateway)


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), change_gateway.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def test_get_seeded_ticket(base_url):
    status, body = get(f"{base_url}/tickets/1001")
    assert status == 200
    assert body["ticket_id"] == "1001"
    assert body["status"] == "pending_review"


def test_sop_violating_ticket_shape(base_url):
    _, body = get(f"{base_url}/tickets/1002")
    # The scale-down below min-replicas scenario the skill must flag.
    assert body["change_type"] == "scale_down"
    assert body["target"]["replicas"] < 2
    assert body["recent_campaign_window"] is not None


def test_unknown_ticket_404(base_url):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{base_url}/tickets/9999")
    assert exc.value.code == 404


def test_metrics_endpoint_with_days_param(base_url):
    cluster = next(iter(change_gateway.METRICS))
    status, body = get(f"{base_url}/metrics/{cluster}?days=14")
    assert status == 200
    assert body["days"] == 14


def test_metrics_unknown_cluster_404(base_url):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{base_url}/metrics/nope.acme.example")
    assert exc.value.code == 404


def test_post_comment_echoes_and_records(base_url):
    comment = {"author": "DE-ACME-CHECKOUT-001", "body": "review: PASS"}
    status, body = post(f"{base_url}/tickets/1001/comments", comment)
    assert status == 201
    assert body["accepted"] is True
    assert body["comment"] == comment
    assert comment in change_gateway.COMMENTS["1001"]


def test_post_comment_unknown_ticket_404(base_url):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(f"{base_url}/tickets/9999/comments", {"body": "x"})
    assert exc.value.code == 404


def test_post_invalid_json_400(base_url):
    req = urllib.request.Request(
        f"{base_url}/tickets/1001/comments",
        data=b"not json",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 400
