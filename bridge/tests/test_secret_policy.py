from __future__ import annotations

import pytest

from bridge.app import DEMO_SIGNING_SECRET, enforce_signing_secret_policy
from bridge.config import BridgeConfig


def make_config(secret: str, host: str) -> BridgeConfig:
    config = BridgeConfig()
    config.chat.signing_secret = secret
    config.server.host = host
    return config


def test_real_secret_passes_on_any_host():
    enforce_signing_secret_policy(make_config("a-real-secret", "0.0.0.0"))


def test_demo_secret_on_loopback_warns_but_starts(caplog):
    with caplog.at_level("WARNING", logger="bridge.app"):
        enforce_signing_secret_policy(make_config(DEMO_SIGNING_SECRET, "127.0.0.1"))
    assert any("demo signing secret" in r.message for r in caplog.records)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::"])
def test_demo_secret_beyond_loopback_refuses_to_start(host):
    with pytest.raises(SystemExit, match="refusing to bind"):
        enforce_signing_secret_policy(make_config(DEMO_SIGNING_SECRET, host))
