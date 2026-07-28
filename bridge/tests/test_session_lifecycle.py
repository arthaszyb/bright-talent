"""Session reaping must never interrupt a turn that is in flight.

Two reapers can stop a subprocess: the idle sweeper and LRU eviction when
`max_sessions` is reached. Both pick their victim by `last_active_at`, and a
turn's timestamp is set when the turn *starts* — so a long-running turn is
exactly the session that looks idlest. Killing it surfaces to the user as
"the agent session ended unexpectedly", a failure that never happened.
These pin that a busy session is left alone while a genuinely idle one is
still reaped.
"""
from __future__ import annotations

import asyncio

from conftest import build_config_dict

from bridge.config import config_from_dict
from bridge.sessions import AGENT_DIED_REPLY, SessionManager


def make_manager(tmp_path, **overrides) -> SessionManager:
    return SessionManager(config_from_dict(build_config_dict(tmp_path, **overrides)))


def test_idle_sweep_does_not_kill_a_turn_in_flight(tmp_path):
    # idle_timeout 0 => every session looks idle the instant it is not touched.
    manager = make_manager(
        tmp_path, sessions={"idle_timeout_seconds": 0, "turn_timeout_seconds": 2}
    )

    async def scenario():
        try:
            turn = asyncio.create_task(manager.send_turn("c:busy", "hang-now please"))
            await asyncio.sleep(0.5)  # let the turn get in flight
            sess = manager._sessions["c:busy"]
            assert sess.is_alive()
            await manager.idle_sweep()
            alive_after_sweep = sess.is_alive()
            return alive_after_sweep, await turn
        finally:
            await manager.shutdown_all()

    alive_after_sweep, reply = asyncio.run(scenario())
    assert alive_after_sweep, "the sweeper killed a session with a turn in flight"
    # The turn ends on its own terms (the fake agent hangs past the turn
    # timeout), never with the subprocess-died reply.
    assert reply != AGENT_DIED_REPLY


def test_idle_sweep_still_reaps_a_genuinely_idle_session(tmp_path):
    manager = make_manager(tmp_path, sessions={"idle_timeout_seconds": 0})

    async def scenario():
        try:
            await manager.send_turn("c:idle", "hello")
            sess = manager._sessions["c:idle"]
            assert sess.is_alive()
            await asyncio.sleep(0.05)  # push last_active_at past the 0s cutoff
            await manager.idle_sweep()
            return sess.is_alive()
        finally:
            await manager.shutdown_all()

    assert asyncio.run(scenario()) is False, "an idle session should still be reaped"


def test_lru_eviction_does_not_evict_a_busy_session(tmp_path):
    # Cap of 1: starting a second session forces an eviction decision while
    # the only live session is mid-turn.
    manager = make_manager(
        tmp_path, sessions={"max_sessions": 1, "turn_timeout_seconds": 2}
    )

    async def scenario():
        try:
            turn = asyncio.create_task(manager.send_turn("c:busy", "hang-now please"))
            await asyncio.sleep(0.5)
            busy = manager._sessions["c:busy"]
            assert busy.is_alive()

            # Second conversation arrives and needs a session.
            await manager.get_or_start("c:other")
            survived = busy.is_alive()
            return survived, await turn
        finally:
            await manager.shutdown_all()

    survived, reply = asyncio.run(scenario())
    assert survived, "LRU eviction killed the session that was mid-turn"
    assert reply != AGENT_DIED_REPLY


def test_turn_start_refreshes_activity_timestamp(tmp_path):
    """A turn must not carry the previous turn's timestamp while it runs."""
    manager = make_manager(tmp_path, sessions={"turn_timeout_seconds": 2})

    async def scenario():
        try:
            await manager.send_turn("c:ts", "hello")
            sess = manager._sessions["c:ts"]
            before = sess.last_active_at
            await asyncio.sleep(0.05)
            turn = asyncio.create_task(manager.send_turn("c:ts", "hang-now please"))
            await asyncio.sleep(0.5)
            during = sess.last_active_at
            await turn
            return before, during
        finally:
            await manager.shutdown_all()

    before, during = asyncio.run(scenario())
    assert during > before, "last_active_at was not refreshed when the turn started"
