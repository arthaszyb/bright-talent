"""Agent-side failure modes: a crashed or hung `claude` subprocess must
produce an explicit user-visible error and a reset session — never an empty
reply or a request that hangs forever."""
from __future__ import annotations

import asyncio
import time

from conftest import build_config_dict

from bridge.config import config_from_dict
from bridge.sessions import AGENT_DIED_REPLY, AGENT_TIMEOUT_REPLY, SessionManager


def make_manager(tmp_path, **overrides) -> SessionManager:
    return SessionManager(config_from_dict(build_config_dict(tmp_path, **overrides)))


def test_crash_mid_turn_reports_error_and_recovers(tmp_path):
    manager = make_manager(tmp_path)

    async def scenario():
        try:
            crashed = await manager.send_turn("c:crash", "please crash-now")
            recovered = await manager.send_turn("c:crash", "hello again")
            return crashed, recovered
        finally:
            await manager.shutdown_all()

    crashed, recovered = asyncio.run(scenario())
    assert crashed == AGENT_DIED_REPLY
    assert recovered == "echo: hello again"


def test_hung_turn_times_out_with_explicit_reply(tmp_path):
    manager = make_manager(tmp_path, sessions={"turn_timeout_seconds": 1})

    async def scenario():
        try:
            return await manager.send_turn("c:hang", "hang-now please")
        finally:
            await manager.shutdown_all()

    start = time.monotonic()
    reply = asyncio.run(scenario())
    elapsed = time.monotonic() - start
    assert reply == AGENT_TIMEOUT_REPLY.format(timeout=1)
    assert elapsed < 10  # bounded by the turn timeout, not the 30s hang


def test_session_respawns_after_timeout(tmp_path):
    manager = make_manager(tmp_path, sessions={"turn_timeout_seconds": 1})

    async def scenario():
        try:
            timed_out = await manager.send_turn("c:retry", "hang-now please")
            retried = await manager.send_turn("c:retry", "second attempt")
            return timed_out, retried
        finally:
            await manager.shutdown_all()

    timed_out, retried = asyncio.run(scenario())
    assert timed_out == AGENT_TIMEOUT_REPLY.format(timeout=1)
    assert retried == "echo: second attempt"
