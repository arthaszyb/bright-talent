"""`de-eval e2e` — command-replay execution (eval-spec.md §5).

For each `tests/*.mock.yaml` case: build a shim dir (fixture command_prefix
first-words + deny-set), start a unix-socket fixture server, spawn the agent
with PATH=<shims>:$PATH against the built runtime, then judge both axes:
execution (command-stream assertions, in-process) and result (semantic
matches, via the LLM judge). Artifacts land under
`eval/runs/<UTC-ts>/<case-id>/`.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from de_eval import agent, judge as judge_mod, paths, shim
from de_eval.fixture_server import FixtureFileError, FixtureServer
from de_eval.yaml_io import UsageError, load_yaml


@dataclass
class CaseVerdict:
    case: str
    case_id: str
    passed: bool
    execution_errors: list[str] = field(default_factory=list)
    semantic_errors: list[str] = field(default_factory=list)
    judge_attempts: dict[str, int] = field(default_factory=dict)
    run_dir: str = ""
    dry_run: bool = False
    shim_names: list[str] = field(default_factory=list)
    fixture_table: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class E2EReport:
    cases: list[CaseVerdict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.cases)


def _load_cases(skill_dir: Path, cases_glob: str | None) -> list[tuple[Path, dict]]:
    tests_dir = skill_dir / "tests"
    pattern = cases_glob or "*.mock.yaml"
    paths_found = sorted(tests_dir.glob(pattern)) if "*" in pattern or "?" in pattern else [tests_dir / pattern]
    cases = []
    for p in paths_found:
        if not p.is_file():
            continue
        if not p.name.endswith(".mock.yaml"):
            continue
        data = load_yaml(p) or {}
        cases.append((p, data))
    return cases


def _fixture_table(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "step": fx.get("step"),
            "command_prefix": fx.get("command_prefix"),
            "exit_code": fx.get("exit_code"),
            "is_fallback": (fx.get("command_prefix") or "") == "",
        }
        for fx in fixtures
    ]


def _run_dir(case_slug: str, ts: str) -> Path:
    d = paths.RUNS_DIR / ts / case_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _check_execution_axis(case_data: dict, commands: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    expected = case_data.get("expected_execution") or {}
    min_commands = int(expected.get("min_replayed_commands", 0))
    required_substrings = expected.get("required_command_substrings") or []
    forbidden_substrings = expected.get("forbidden_command_substrings") or []

    matched_commands = [c for c in commands if c.get("matched")]
    unmatched = [c for c in commands if not c.get("matched")]

    if unmatched:
        names = ", ".join(c["command"] for c in unmatched)
        errors.append(f"unmatched-command error: no fixture matched: {names}")

    if len(matched_commands) < min_commands:
        errors.append(
            f"min_replayed_commands: expected >= {min_commands}, got {len(matched_commands)}"
        )

    all_cmd_text = "\n".join(c["command"] for c in commands)
    for sub in required_substrings:
        if sub not in all_cmd_text:
            errors.append(f"required_command_substrings: missing '{sub}' in replayed commands")
    for sub in forbidden_substrings:
        for c in commands:
            if sub in c["command"]:
                errors.append(f"forbidden_command_substrings: found '{sub}' in command '{c['command']}'")

    return errors


def run_case(
    case_path: Path,
    case_data: dict,
    skill_dir: Path,
    runtime_dir: Path,
    scope_service_catalog: str,
    ts: str,
    dry_run: bool = False,
) -> CaseVerdict:
    case_slug = case_data.get("case") or case_path.stem
    evaluation = case_data.get("evaluation") or {}
    case_id = evaluation.get("case_id", case_slug)
    fixtures = case_data.get("fixtures") or []

    run_dir = _run_dir(case_slug, ts)
    commands_jsonl = run_dir / ".commands.jsonl"
    transcript_jsonl = run_dir / "transcript.jsonl"
    shim_dir = run_dir / "shims"
    # AF_UNIX paths are capped (~104 bytes on macOS/BSD); eval/runs/<ts>/<case>/
    # under a deep repo checkout routinely blows that budget, so the socket
    # itself lives in a short-named system tmpdir while every spec-mandated
    # artifact (.commands.jsonl, transcript.jsonl, shims/) stays under
    # eval/runs/<UTC-ts>/<case-id>/ as required.
    sock_tmp_dir = Path(tempfile.mkdtemp(prefix="de-eval-"))
    sock_path = sock_tmp_dir / "fixture.sock"

    verdict = CaseVerdict(
        case=case_slug,
        case_id=case_id,
        passed=False,
        run_dir=str(run_dir),
        dry_run=dry_run,
        fixture_table=_fixture_table(fixtures),
    )

    try:
        server = FixtureServer(fixtures, commands_jsonl, sock_path)
    except FixtureFileError as e:
        verdict.execution_errors.append(str(e))
        return verdict

    names = shim.shim_names_for_case(fixtures)
    verdict.shim_names = sorted(names)
    shim.write_shims(shim_dir, names)

    server.start()
    try:
        if dry_run:
            verdict.passed = True
            return verdict

        env = agent.env_floor(runtime_dir, scope_service_catalog, dict(os.environ))
        env["PATH"] = f"{shim_dir}:{env.get('PATH', '')}"
        env["DE_EVAL_FIXTURE_SOCK"] = str(sock_path.resolve())

        run = agent.run_agent(case_data["prompt"], runtime_dir, env)
        transcript_jsonl.write_text("\n".join(run.raw_lines) + "\n", encoding="utf-8")

        commands: list[dict[str, Any]] = []
        if commands_jsonl.is_file():
            for line in commands_jsonl.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    import json

                    commands.append(json.loads(line))

        verdict.execution_errors = _check_execution_axis(case_data, commands)

        expected_result = case_data.get("expected_result") or {}
        final_answer = run.final_text()
        for literal in expected_result.get("required_output_contains") or []:
            if literal not in final_answer:
                verdict.semantic_errors.append(f"required_output_contains: missing literal '{literal}'")

        skill_md_text = (
            (skill_dir / "SKILL.md").read_text(encoding="utf-8") if (skill_dir / "SKILL.md").is_file() else ""
        )
        for i, assertion in enumerate(expected_result.get("required_output_semantic_matches") or []):
            jv = judge_mod.judge_assertion(
                assertion=assertion,
                case_prompt=case_data.get("prompt", ""),
                transcript_text="\n".join(run.raw_lines),
                final_answer=final_answer,
                skill_md_text=skill_md_text,
            )
            verdict.judge_attempts[f"semantic[{i}]"] = jv.attempts
            if not jv.passed:
                verdict.semantic_errors.append(f"semantic match failed: '{assertion}' -- {jv.reason}")

        verdict.passed = not verdict.execution_errors and not verdict.semantic_errors
        return verdict
    finally:
        server.stop()
        import shutil as _shutil

        _shutil.rmtree(sock_tmp_dir, ignore_errors=True)


def run_e2e(
    skill_dir: Path,
    scope_service_catalog: str,
    cases_glob: str | None = None,
    dry_run: bool = False,
    rebuild_fixture: bool = False,
) -> E2EReport:
    from de_eval.fixture_runtime import ensure_fixture_runtime

    runtime_dir = ensure_fixture_runtime(skill_dir, rebuild=rebuild_fixture)
    cases = _load_cases(skill_dir, cases_glob)
    if not cases:
        raise UsageError(f"no *.mock.yaml cases found under {skill_dir / 'tests'}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = E2EReport()
    for case_path, case_data in cases:
        verdict = run_case(case_path, case_data, skill_dir, runtime_dir, scope_service_catalog, ts, dry_run=dry_run)
        report.cases.append(verdict)
    return report
