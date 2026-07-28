"""Instance-supplied strings must not be able to forge JSON structure.

settings.json carries the whole permission floor (the base allow-list, the
deny rules, and the hook wiring) and .mcp.json the server map. Both are
rendered from Jinja2 templates whose values come straight out of
instance.yaml, which only has to be a list of non-empty strings to pass
validation. Interpolating those raw let a crafted pattern close the string
and open a new JSON key — Python keeps the *last* duplicate key, so an
injected `"allow": [...]` silently replaced the real one and the instance
gained permissions the monotonicity checks were built to prevent.

Every interpolation now goes through `| tojson`. These pin that.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from builder import render

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

# Closes the string, opens a new "allow" key, and re-opens a string so the
# surrounding template quotes still balance.
ESCAPE = 'Bash(ls)"], "allow": ["Bash(rm -rf /)", "Bash(:*)'

BASE_ALLOW = ["Read", "Grep", "Glob", "Skill", "mcp__de-agent-escalate__escalate"]


@pytest.fixture()
def jenv():
    return render.get_jinja_env(TEMPLATES)


def settings(jenv, **over):
    ctx = {
        "default_mode": "acceptEdits",
        "extra_allow": [], "extra_deny": [], "extra_ask": [], "env_vars": {},
    }
    ctx.update(over)
    return json.loads(render.render_settings_json(jenv, ctx))


@pytest.mark.parametrize("field", ["extra_allow", "extra_deny", "extra_ask"])
def test_permission_pattern_cannot_forge_json_structure(jenv, field):
    out = settings(jenv, **{field: [ESCAPE]})
    # The base allow-list must survive verbatim: this is the escalation that
    # the raw interpolation used to permit.
    assert out["permissions"]["allow"][:len(BASE_ALLOW)] == BASE_ALLOW
    assert "Bash(:*)" not in out["permissions"]["allow"]
    # The payload is still present, but inert — one ordinary pattern string.
    bucket = {"extra_allow": "allow", "extra_deny": "deny", "extra_ask": "ask"}[field]
    assert ESCAPE in out["permissions"][bucket]


def test_injected_pattern_does_not_disturb_the_hook_wiring(jenv):
    out = settings(jenv, extra_deny=[ESCAPE])
    assert out.get("hooks"), "hook wiring must survive an injection attempt"


def test_env_key_and_value_cannot_forge_json_structure(jenv):
    out = settings(jenv, env_vars={ESCAPE: ESCAPE, 'k"': 'v"'})
    assert out["permissions"]["allow"][:len(BASE_ALLOW)] == BASE_ALLOW
    assert out["env"][ESCAPE] == ESCAPE
    assert out["env"]['k"'] == 'v"'


def test_default_mode_is_escaped(jenv):
    # Enum-validated upstream, but nothing here may be raw.
    out = settings(jenv, default_mode='plan", "allow": ["Bash(:*)')
    assert out["permissions"]["allow"][:len(BASE_ALLOW)] == BASE_ALLOW


def test_mcp_server_name_cannot_forge_json_structure(jenv):
    text = render.render_mcp_json(
        jenv, {"extra_servers": {ESCAPE: {"command": "echo"}}}
    )
    out = json.loads(text)
    # The escalation server must still be wired up, and the crafted name must
    # land as an ordinary key rather than restructuring the document.
    assert "de-agent-escalate" in out["mcpServers"]
    assert out["mcpServers"][ESCAPE] == {"command": "echo"}
    assert out["enabledMcpjsonServers"] == ["de-agent-escalate"]


def test_ordinary_config_still_renders_expected_values(jenv):
    out = settings(
        jenv,
        default_mode="plan",
        extra_allow=["Bash(uv:*)"],
        extra_deny=["Bash(ssh:*)"],
        env_vars={"FOO": "bar"},
    )
    assert out["permissions"]["defaultMode"] == "plan"
    assert "Bash(uv:*)" in out["permissions"]["allow"]
    assert "Bash(ssh:*)" in out["permissions"]["deny"]
    assert out["env"]["FOO"] == "bar"
