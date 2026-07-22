from __future__ import annotations

import asyncio

from bridge import commands


class FakeSessions:
    """Records the SessionManager calls handle_command makes."""

    def __init__(self, working_dir="/work"):
        self.reset_keys = []
        self.cwd_overrides = {}
        self.mode_overrides = {}
        self._working_dir = working_dir

    async def reset_async(self, key):
        self.reset_keys.append(key)

    def set_cwd_override(self, key, path):
        self.cwd_overrides[key] = path

    def get_working_dir(self, key):
        return self._working_dir

    def set_permission_mode_override(self, key, mode):
        self.mode_overrides[key] = mode


def run(text, sessions, **kw):
    return asyncio.run(commands.handle_command(text, "chan:thread", sessions, **kw))


# ---- is_command ------------------------------------------------------------

def test_is_command_recognizes_known_tokens():
    assert commands.is_command("/help")
    assert commands.is_command("/mode acceptEdits")
    assert not commands.is_command("hello")
    assert not commands.is_command("")
    assert not commands.is_command("/helpfoo")  # not a bare token


# ---- dispatch --------------------------------------------------------------

def test_help_and_pwd_and_reset():
    s = FakeSessions(working_dir="/runtime")
    assert "reset" in run("/help", s).lower()
    assert run("/pwd", s) == "/runtime"
    assert run("/reset", s) == "Session reset."
    assert s.reset_keys == ["chan:thread"]


def test_cd_sets_override_and_needs_arg():
    s = FakeSessions()
    assert "Usage" in run("/cd", s)
    run("/cd /tmp/x", s)
    assert s.cwd_overrides["chan:thread"] == "/tmp/x"


def test_plan_sets_strictest_mode():
    s = FakeSessions()
    run("/plan", s)
    assert s.mode_overrides["chan:thread"] == "plan"


def test_mode_rejects_invalid():
    s = FakeSessions()
    assert "Usage" in run("/mode wild", s)
    assert s.mode_overrides == {}


def test_unknown_command():
    assert run("/nope", FakeSessions()).startswith("Unknown command")


# ---- permission monotonicity (the escalation gate) -------------------------

def test_nonadmin_may_tighten_to_stricter_mode():
    s = FakeSessions()
    # base acceptEdits; plan/default are stricter -> allowed for non-admin
    run("/mode plan", s, is_admin=False, base_mode="acceptEdits")
    run("/mode default", s, is_admin=False, base_mode="acceptEdits")
    assert s.mode_overrides["chan:thread"] == "default"


def test_nonadmin_may_set_equal_mode():
    s = FakeSessions()
    run("/mode acceptEdits", s, is_admin=False, base_mode="acceptEdits")
    assert s.mode_overrides["chan:thread"] == "acceptEdits"


def test_nonadmin_cannot_loosen_beyond_base():
    s = FakeSessions()
    reply = run("/mode bypassPermissions", s, is_admin=False, base_mode="acceptEdits")
    assert reply == commands.PERMISSION_ESCALATION_MESSAGE
    assert s.mode_overrides == {}  # override NOT applied


def test_admin_may_loosen():
    s = FakeSessions()
    run("/mode bypassPermissions", s, is_admin=True, base_mode="acceptEdits")
    assert s.mode_overrides["chan:thread"] == "bypassPermissions"


def test_loosens_beyond_ordering():
    assert commands.loosens_beyond("bypassPermissions", "acceptEdits") is True
    assert commands.loosens_beyond("plan", "acceptEdits") is False
    assert commands.loosens_beyond("acceptEdits", "acceptEdits") is False
    assert commands.loosens_beyond("bogus", "acceptEdits") is False
