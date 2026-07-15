"""`de-eval triggers` (eval-spec.md §3)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from de_eval import agent
from de_eval.yaml_io import UsageError, load_yaml

DEFAULT_PASS_THRESHOLD = 0.9


@dataclass
class CaseResult:
    case_id: str
    prompt: str
    expected: str  # "should_trigger" | "should_not_trigger"
    triggered: bool
    passed: bool


@dataclass
class TriggersReport:
    results: list[CaseResult] = field(default_factory=list)
    pass_threshold: float = DEFAULT_PASS_THRESHOLD

    @property
    def ratio(self) -> float:
        if not self.results:
            return 1.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    @property
    def ok(self) -> bool:
        return self.ratio >= self.pass_threshold


def run_triggers(
    skill_dir: Path,
    runtime_dir: Path,
    scope_service_catalog: str,
    cases_glob: str | None = None,
) -> TriggersReport:
    triggers_path = skill_dir / "tests" / "triggers.yaml"
    data = load_yaml(triggers_path) or {}
    skill_name = skill_dir.name
    pass_threshold = float(data.get("pass_threshold", DEFAULT_PASS_THRESHOLD))
    report = TriggersReport(pass_threshold=pass_threshold)

    env = agent.env_floor(runtime_dir, scope_service_catalog, dict(os.environ))

    def matches_glob(case_id: str) -> bool:
        if not cases_glob:
            return True
        import fnmatch

        return fnmatch.fnmatch(case_id, cases_glob)

    for kind, expect_trigger in (("should_trigger", True), ("should_not_trigger", False)):
        for case in data.get(kind) or []:
            evaluation = case.get("evaluation") or {}
            case_id = evaluation.get("case_id", "<unlabeled>")
            if not matches_glob(case_id):
                continue
            run = agent.run_agent(case["prompt"], runtime_dir, env)
            triggered = agent.skill_triggered(run, skill_name)
            passed = triggered == expect_trigger
            report.results.append(
                CaseResult(
                    case_id=case_id,
                    prompt=case["prompt"],
                    expected=kind,
                    triggered=triggered,
                    passed=passed,
                )
            )
    return report
