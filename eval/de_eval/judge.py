"""LLM-judge invocation (eval-spec.md §5.3, normative judge invocation).

`claude -p --model <judge_model>` with no tools, prompted for a strict JSON
verdict `{"pass": bool, "reason": str}`. One retry on parse failure or judge
error (count pinned by eval/judge.toml `[judge] retry`); retries are
recorded in the returned JudgeVerdict for the report.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field

from de_eval import paths
from de_eval.yaml_io import load_toml

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class JudgeVerdict:
    passed: bool
    reason: str
    attempts: int = 1
    errors: list[str] = field(default_factory=list)


def load_judge_config() -> dict:
    cfg = load_toml(paths.JUDGE_TOML)
    judge = cfg.get("judge") or {}
    return {"model": judge.get("model", "claude-haiku-4-5"), "retry": int(judge.get("retry", 1))}


def _build_judge_prompt(
    assertion: str,
    case_prompt: str,
    transcript_text: str,
    final_answer: str,
    skill_md_text: str,
) -> str:
    return f"""You are grading a single assertion about an AI agent's behavior in an
evaluation harness. Answer with STRICT JSON only, no other text, exactly:
{{"pass": true|false, "reason": "<one sentence>"}}

## Assertion to grade
{assertion}

## Skill definition (SKILL.md) — decision rubric context
{skill_md_text}

## Case prompt (what the user asked)
{case_prompt}

## Transcript (tool calls and outputs)
{transcript_text}

## Agent's final answer
{final_answer}

Grade strictly against the assertion text. Output only the JSON object."""


def _call_claude_judge(prompt: str, model: str, timeout: int = 120) -> str:
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "text"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"judge call failed (exit {proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _parse_verdict(raw: str) -> tuple[bool, str]:
    match = _JSON_RE.search(raw)
    if not match:
        raise ValueError(f"judge output is not JSON: {raw!r}")
    data = json.loads(match.group(0))
    if "pass" not in data:
        raise ValueError(f"judge JSON missing 'pass' key: {data!r}")
    return bool(data["pass"]), str(data.get("reason", ""))


def judge_assertion(
    assertion: str,
    case_prompt: str,
    transcript_text: str,
    final_answer: str,
    skill_md_text: str,
    model: str | None = None,
    retry: int | None = None,
) -> JudgeVerdict:
    cfg = load_judge_config()
    model = model or cfg["model"]
    retry = cfg["retry"] if retry is None else retry

    prompt = _build_judge_prompt(assertion, case_prompt, transcript_text, final_answer, skill_md_text)
    errors: list[str] = []
    attempts = 0
    max_attempts = 1 + max(retry, 0)
    while attempts < max_attempts:
        attempts += 1
        try:
            raw = _call_claude_judge(prompt, model)
            passed, reason = _parse_verdict(raw)
            return JudgeVerdict(passed=passed, reason=reason, attempts=attempts, errors=errors)
        except Exception as e:  # noqa: BLE001 - judge failures are recorded, not fatal
            errors.append(str(e))
    return JudgeVerdict(
        passed=False,
        reason=f"judge failed after {attempts} attempt(s): {errors[-1] if errors else 'unknown error'}",
        attempts=attempts,
        errors=errors,
    )
