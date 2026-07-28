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


# ---- verdict coercion: a "fail" must never read as a pass -------------------

@pytest.mark.parametrize("literal", ['"false"', '"no"', '"FAIL"', '"False"', '" false "', "0"])
def test_negative_verdicts_are_never_read_as_pass(literal):
    """bool("false") is True — the judge's rejection used to become a PASS.

    The judge model quoting its boolean is an ordinary formatting slip, and
    it silently turned a failing safety assertion into a green release gate
    with no exception, no retry, and nothing recorded in errors.
    """
    passed, _ = judge._parse_verdict('{"pass": %s, "reason": "agent refused nothing"}' % literal)
    assert passed is False


@pytest.mark.parametrize("literal", ['"true"', '"yes"', '"PASS"', "true", "1"])
def test_affirmative_verdicts_still_pass(literal):
    passed, _ = judge._parse_verdict('{"pass": %s, "reason": "ok"}' % literal)
    assert passed is True


@pytest.mark.parametrize("literal", ['"maybe"', "null", "2", '{"nested": 1}', '[]'])
def test_ambiguous_verdicts_are_rejected(literal):
    # Rejected, not guessed: the retry gives the judge another chance and an
    # exhausted retry fails closed.
    with pytest.raises(ValueError):
        judge._parse_verdict('{"pass": %s, "reason": "x"}' % literal)


def test_ambiguous_verdict_fails_closed_through_the_retry_path(pinned_config, monkeypatch):
    monkeypatch.setattr(
        judge, "_call_claude_judge", lambda prompt, model: '{"pass": "maybe", "reason": "unsure"}'
    )
    v = judge.judge_assertion("a", "p", "t", "f", "s")
    assert v.passed is False
    assert v.attempts == 2
    assert v.errors, "the unparseable verdict should be recorded for the report"


def test_quoted_false_reaches_the_caller_as_a_failure(pinned_config, monkeypatch):
    monkeypatch.setattr(
        judge,
        "_call_claude_judge",
        lambda prompt, model: '{"pass": "false", "reason": "the agent approved the ticket"}',
    )
    v = judge.judge_assertion("a", "p", "t", "f", "s")
    assert v.passed is False
    assert v.attempts == 1  # parsed fine — it is a valid verdict, just negative
    assert v.reason == "the agent approved the ticket"
