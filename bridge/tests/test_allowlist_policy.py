"""Startup policy: warn when the bridge has no user allowlist.

`auth.is_allowed` fail-opens on an empty `allowed_users`, so any
signature-valid sender can drive the agent. enforce_allowlist_policy makes
that visible at boot — a plain warning on loopback, an escalated one off-box.
It never fails the process (unlike the signing-secret policy), because a real
signing secret already gates delivery, so an open user list may be deliberate.
"""
from __future__ import annotations

import pytest

from bridge.app import enforce_allowlist_policy
from bridge.config import BridgeConfig


def make_config(allowed_users: list[str], host: str) -> BridgeConfig:
    config = BridgeConfig()
    config.auth.allowed_users = allowed_users
    config.server.host = host
    return config


def test_configured_allowlist_is_silent(caplog):
    with caplog.at_level("WARNING", logger="bridge.app"):
        enforce_allowlist_policy(make_config(["demo-user"], "0.0.0.0"))
    assert caplog.records == []


def test_empty_allowlist_on_loopback_warns(caplog):
    with caplog.at_level("WARNING", logger="bridge.app"):
        enforce_allowlist_policy(make_config([], "127.0.0.1"))
    assert any("no user allowlist" in r.message for r in caplog.records)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::"])
def test_empty_allowlist_beyond_loopback_warns_loudly_but_starts(host, caplog):
    with caplog.at_level("WARNING", logger="bridge.app"):
        enforce_allowlist_policy(make_config([], host))
    # Escalated wording naming the host — but no SystemExit is raised.
    assert any("EMPTY user allowlist" in r.message for r in caplog.records)
