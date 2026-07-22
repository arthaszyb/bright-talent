from __future__ import annotations

import pytest

from de_eval import judge


def test_parse_verdict_strict_json():
    passed, reason = judge._parse_verdict('{"pass": true, "reason": "ok"}')
    assert passed is True and reason == "ok"


def test_parse_verdict_extracts_json_from_noise():
    raw = 'Sure, here is the verdict:\n{"pass": false, "reason": "policy cited"}\nDone.'
    passed, reason = judge._parse_verdict(raw)
    assert passed is False and reason == "policy cited"


def test_parse_verdict_rejects_non_json():
    with pytest.raises(ValueError, match="not JSON"):
        judge._parse_verdict("PASS")


def test_parse_verdict_rejects_missing_pass_key():
    with pytest.raises(ValueError, match="missing 'pass'"):
        judge._parse_verdict('{"reason": "no verdict"}')


@pytest.fixture()
def pinned_config(monkeypatch):
    monkeypatch.setattr(judge, "load_judge_config", lambda: {"model": "judge-model", "retry": 1})


def test_judge_assertion_happy_path(pinned_config, monkeypatch):
    monkeypatch.setattr(
        judge, "_call_claude_judge", lambda prompt, model: '{"pass": true, "reason": "grounded"}'
    )
    v = judge.judge_assertion("a", "p", "t", "f", "s")
    assert v.passed is True and v.attempts == 1 and v.errors == []


def test_judge_assertion_retries_once_then_succeeds(pinned_config, monkeypatch):
    calls = []

    def flaky(prompt, model):
        calls.append(model)
        if len(calls) == 1:
            return "garbage, not json"
        return '{"pass": true, "reason": "second try"}'

    monkeypatch.setattr(judge, "_call_claude_judge", flaky)
    v = judge.judge_assertion("a", "p", "t", "f", "s")
    assert v.passed is True and v.attempts == 2
    assert len(v.errors) == 1  # the first failure is recorded for the report


def test_judge_assertion_fails_closed_after_retries(pinned_config, monkeypatch):
    def always_broken(prompt, model):
        raise RuntimeError("judge call failed (exit 1)")

    monkeypatch.setattr(judge, "_call_claude_judge", always_broken)
    v = judge.judge_assertion("a", "p", "t", "f", "s")
    assert v.passed is False
    assert v.attempts == 2  # 1 + retry pinned to 1
    assert "judge failed after 2 attempt(s)" in v.reason


def test_judge_assertion_zero_retry_is_single_attempt(pinned_config, monkeypatch):
    def always_broken(prompt, model):
        raise RuntimeError("boom")

    monkeypatch.setattr(judge, "_call_claude_judge", always_broken)
    v = judge.judge_assertion("a", "p", "t", "f", "s", retry=0)
    assert v.passed is False and v.attempts == 1
