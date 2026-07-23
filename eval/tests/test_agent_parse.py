"""Tests for the stream-json transcript parsers (de_eval/agent.py).

tool_uses / final_text / skill_triggered are what every eval gate uses to
decide whether a skill fired and which tools ran. They are pure functions
over the recorded frames (run_agent, which needs a live claude CLI, is not
exercised here) — a regression here would silently corrupt every triggers /
safety / e2e result, so pin them directly.
"""
from __future__ import annotations

from de_eval.agent import AgentRun, _contains_skill_name, skill_triggered


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def tool_use(name, tool_input):
    return {"type": "tool_use", "name": name, "input": tool_input}


def text(t):
    return {"type": "text", "text": t}


def run(*frames):
    return AgentRun(returncode=0, frames=list(frames))


# ---- tool_uses -------------------------------------------------------------

def test_tool_uses_collects_across_frames():
    r = run(
        assistant(tool_use("Read", {"path": "a"})),
        assistant(text("thinking"), tool_use("Skill", {"command": "ticket-review"})),
    )
    uses = r.tool_uses()
    assert [u["name"] for u in uses] == ["Read", "Skill"]


def test_tool_uses_ignores_non_list_content_and_missing_message():
    r = run(
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": "not-a-list"}},
        assistant(text("no tools here")),
    )
    assert r.tool_uses() == []


# ---- final_text ------------------------------------------------------------

def test_final_text_prefers_result_frame():
    r = run(
        assistant(text("intermediate")),
        {"type": "result", "result": "the authoritative answer"},
    )
    assert r.final_text() == "the authoritative answer"


def test_final_text_falls_back_to_last_assistant_text():
    r = run(
        assistant(text("first")),
        assistant(text("second"), text("line")),
    )
    assert r.final_text() == "second\nline"


def test_final_text_empty_when_nothing():
    assert run({"type": "system"}).final_text() == ""


def test_final_text_ignores_non_string_result():
    r = run(
        assistant(text("fallback text")),
        {"type": "result", "result": {"not": "a string"}},
    )
    assert r.final_text() == "fallback text"


# ---- skill_triggered -------------------------------------------------------

def test_skill_triggered_true_on_matching_skill_input():
    r = run(assistant(tool_use("Skill", {"command": "ticket-review"})))
    assert skill_triggered(r, "ticket-review") is True


def test_skill_triggered_case_insensitive_tool_name():
    r = run(assistant(tool_use("skill", {"name": "ticket-review"})))
    assert skill_triggered(r, "ticket-review") is True


def test_skill_triggered_false_when_skill_not_referenced():
    r = run(assistant(tool_use("Skill", {"command": "some-other-skill"})))
    assert skill_triggered(r, "ticket-review") is False


def test_skill_triggered_false_for_non_skill_tool():
    # A non-Skill tool that merely mentions the name must not count as a trigger.
    r = run(assistant(tool_use("Bash", {"command": "cat ticket-review notes"})))
    assert skill_triggered(r, "ticket-review") is False


def test_skill_triggered_finds_name_in_nested_input():
    r = run(assistant(tool_use("Skill", {"args": {"opts": ["ticket-review"]}})))
    assert skill_triggered(r, "ticket-review") is True


# ---- _contains_skill_name --------------------------------------------------

def test_contains_skill_name_recurses_str_dict_list():
    assert _contains_skill_name("use ticket-review now", "ticket-review") is True
    assert _contains_skill_name({"a": {"b": "ticket-review"}}, "ticket-review") is True
    assert _contains_skill_name(["x", ["y", "ticket-review"]], "ticket-review") is True
    assert _contains_skill_name({"a": 1, "b": None}, "ticket-review") is False
