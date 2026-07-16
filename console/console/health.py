"""Health score + 4-state status (docs/60-console/design.md §"Health Score Algorithm").

Implemented exactly per the spec's deduction/precedence tables (per
de-demo/DESIGN.md §S7: "no reinterpretation").
"""
from __future__ import annotations

from typing import Any

DEDUCTION_BASE_STALE = 20
DEDUCTION_MANAGED_DRIFT = 20
DEDUCTION_CI_UNAVAILABLE = 10
DEDUCTION_CI_FAIL = 20
DEDUCTION_MISSING_FILES = 15
DEDUCTION_NO_SKILLS = 5


def _managed_files_drifted(scan: dict[str, Any]) -> bool:
    return any(f["status"] != "up_to_date" for f in scan.get("managed_files", []))


def _managed_files_conflict(scan: dict[str, Any]) -> bool:
    return any(f["status"] == "both_changed" for f in scan.get("managed_files", []))


def _ci_failed(ci: dict[str, Any]) -> bool:
    return any(step.get("status") == "fail" for step in ci.get("steps", []))


def score_instance(scan: dict[str, Any], ci: dict[str, Any]) -> dict[str, Any]:
    """Returns {"score": int, "deductions": [{"reason": str, "points": int}]}."""
    deductions: list[dict[str, Any]] = []

    if scan.get("base", {}).get("status") == "stale":
        deductions.append({"reason": "base_stale", "points": DEDUCTION_BASE_STALE})
    if _managed_files_drifted(scan):
        deductions.append({"reason": "managed_file_drift", "points": DEDUCTION_MANAGED_DRIFT})
    if not ci.get("available"):
        deductions.append({"reason": "ci_unavailable", "points": DEDUCTION_CI_UNAVAILABLE})
    if _ci_failed(ci):
        deductions.append({"reason": "ci_failed", "points": DEDUCTION_CI_FAIL})
    if not scan.get("files", {}).get("instance_yaml") or not scan.get("files", {}).get("version"):
        deductions.append({"reason": "missing_identity_files", "points": DEDUCTION_MISSING_FILES})
    if not scan.get("skills"):
        deductions.append({"reason": "no_skills", "points": DEDUCTION_NO_SKILLS})

    total = sum(d["points"] for d in deductions)
    score = max(0, min(100, 100 - total))
    return {"score": score, "deductions": deductions}


def status_for_instance(scan: dict[str, Any], ci: dict[str, Any], score: int) -> str:
    if _managed_files_conflict(scan):
        return "conflict"
    if score < 75 or not ci.get("available"):
        return "risk"
    if scan.get("base", {}).get("status") == "stale" or _managed_files_drifted(scan):
        return "warn"
    return "healthy"


def score_color(score: int) -> str:
    if score >= 85:
        return "green"
    if score >= 70:
        return "amber"
    return "red"


def score_label(score: int) -> str:
    if score >= 85:
        return "production-ready"
    if score >= 70:
        return "needs review"
    return "high risk"


def evaluate(scan: dict[str, Any], ci: dict[str, Any]) -> dict[str, Any]:
    result = score_instance(scan, ci)
    score = result["score"]
    status = status_for_instance(scan, ci, score)
    return {
        "score": score,
        "deductions": result["deductions"],
        "status": status,
        "color": score_color(score),
        "label": score_label(score),
    }
