from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.app import create_app  # noqa: E402
from bridge.config import config_from_dict  # noqa: E402

TEST_SECRET = "test-signing-secret"
FAKE_CLAUDE = Path(__file__).resolve().parent / "fake_claude.py"


def sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def build_config_dict(tmp_path: Path, **overrides) -> dict:
    cfg = {
        "chat": {
            "app_id": "test-app",
            "signing_secret": TEST_SECRET,
            "api_base_url": "",
            "bot_id": "test-bot",
        },
        "server": {
            "host": "127.0.0.1",
            "port": 9100,
            "pid_file": str(tmp_path / "log" / "bridge-http.pid"),
        },
        "agent": {
            "claude_cmd": f"{sys.executable} {FAKE_CLAUDE}",
            "permission_mode": "acceptEdits",
            "extra_args": [],
            "env": {},
        },
        "sessions": {
            "idle_timeout_seconds": 60,
            "max_sessions": 20,
            "working_dir": str(tmp_path / "runtime"),
            "data_dir": str(tmp_path / "data"),
        },
        "auth": {"allowed_users": [], "admin_users": []},
        "memory": {
            "enabled": True,
            "context_min_chars": 5,
            "context_max_chars": 2000,
            "context_max_results": 3,
        },
        "reply_transport": "log+callback",
    }
    for key, value in overrides.items():
        cfg[key].update(value)
    return cfg


@pytest.fixture
def bridge_app_factory(tmp_path):
    created = []

    def _factory(**overrides):
        cfg_dict = build_config_dict(tmp_path, **overrides)
        config = config_from_dict(cfg_dict)
        app = create_app(config)
        created.append(app)
        return app, config

    yield _factory

    for app in created:
        sessions = app.state.sessions
        import asyncio

        asyncio.run(sessions.shutdown_all())


@pytest.fixture
def client(bridge_app_factory):
    app, config = bridge_app_factory()
    with TestClient(app) as c:
        c.bridge_config = config
        yield c
