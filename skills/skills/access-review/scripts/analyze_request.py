#!/usr/bin/env python3
"""Apply the least-privilege access policy to a service access-grant request.

Reads an access-request JSON (from a file path, or stdin if the path is
omitted / "-") and the bundled policy (policy/access-policy.json by default),
applies three illustrative least-privilege rules, and prints a single JSON
object to stdout:

  {
    "request_id": ...,
    "requestor": ...,
    "service": ...,
    "role": ...,
    "environment": ...,
    "checks": [
      {"rule": "...", "status": "pass|warn|fail", "evidence": "..."},
      ...
    ],
    "summary": "pass|warn|fail"   # worst status across all checks
  }

Rules (illustrative; see kb/team/runbooks/access-review-policy.md for the
human-readable version):
  R1  requested role must exist in the service's role catalog
      (no unknown / over-broad roles).
  R2  a production grant must cite a justification ticket AND be time-boxed
      to at most `max_prod_grant_days` days (no standing production access).
  R3  a privileged role (operator/admin) on a PII-classified service in
      production requires an explicit manager approval.

This skill never grants or revokes access. It emits a review comment for a
human approver.

Usage:
  uv run python scripts/analyze_request.py --request /tmp/req.json
  cat req.json | uv run python scripts/analyze_request.py --request -
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

STATUS_ORDER = {"pass": 0, "warn": 1, "fail": 2}


def _worst(statuses: list[str]) -> str:
    return max(statuses, key=lambda s: STATUS_ORDER.get(s, 0)) if statuses else "pass"


def _load_json(path: str) -> Any:
    if path in ("-", None):
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _check_role_in_catalog(request: dict, service_policy: dict | None) -> dict:
    rule = "requested_role_in_service_catalog"
    service = request.get("service")
    role = request.get("role")
    if service_policy is None:
        return {
            "rule": rule,
            "status": "fail",
            "evidence": f"service {service!r} is not in the access policy catalog",
        }
    allowed = service_policy.get("roles", [])
    if role in allowed:
        return {
            "rule": rule,
            "status": "pass",
            "evidence": f"role {role!r} is in the catalog for {service} (allowed: {', '.join(allowed)})",
        }
    return {
        "rule": rule,
        "status": "fail",
        "evidence": f"role {role!r} is not in the catalog for {service} (allowed: {', '.join(allowed)})",
    }


def _check_prod_time_boxed(request: dict, max_days: int) -> dict:
    rule = "production_grant_time_boxed"
    env = request.get("environment")
    if env != "production":
        return {
            "rule": rule,
            "status": "pass",
            "evidence": f"environment={env!r}; production time-box rule not applicable",
        }
    ticket = request.get("justification_ticket")
    duration = request.get("duration_days")
    problems = []
    if not ticket:
        problems.append("no justification_ticket cited")
    if duration is None:
        problems.append("no duration_days (standing access is not permitted)")
    elif not isinstance(duration, (int, float)) or duration <= 0:
        problems.append(f"duration_days={duration!r} is not a positive number")
    elif duration > max_days:
        problems.append(f"duration_days={duration} exceeds the {max_days}-day production cap")
    if problems:
        return {"rule": rule, "status": "fail", "evidence": "; ".join(problems)}
    return {
        "rule": rule,
        "status": "pass",
        "evidence": f"production grant cites {ticket} and is time-boxed to {duration} day(s) (cap {max_days})",
    }


def _check_privileged_pii(request: dict, service_policy: dict | None, privileged_roles: list[str]) -> dict:
    rule = "privileged_pii_requires_manager_approval"
    role = request.get("role")
    env = request.get("environment")
    classification = (service_policy or {}).get("classification", "standard")
    privileged = role in privileged_roles
    if not (privileged and classification == "pii" and env == "production"):
        return {
            "rule": rule,
            "status": "pass",
            "evidence": (
                f"role={role!r}, classification={classification!r}, environment={env!r}; "
                "manager-approval rule not applicable"
            ),
        }
    if request.get("manager_approved") is True:
        return {
            "rule": rule,
            "status": "pass",
            "evidence": f"privileged {role} on PII service in production carries manager approval",
        }
    return {
        "rule": rule,
        "status": "fail",
        "evidence": (
            f"privileged {role} on a PII-classified service in production requires "
            "manager_approved=true, which is absent"
        ),
    }


def analyze(request: dict, policy: dict) -> dict:
    services = policy.get("services", {})
    service_policy = services.get(request.get("service"))
    privileged_roles = policy.get("privileged_roles", [])
    max_days = int(policy.get("rules", {}).get("max_prod_grant_days", 90))

    checks = [
        _check_role_in_catalog(request, service_policy),
        _check_prod_time_boxed(request, max_days),
        _check_privileged_pii(request, service_policy, privileged_roles),
    ]
    return {
        "request_id": request.get("request_id"),
        "requestor": request.get("requestor"),
        "service": request.get("service"),
        "role": request.get("role"),
        "environment": request.get("environment"),
        "checks": checks,
        "summary": _worst([c["status"] for c in checks]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default="-", help="path to the access-request JSON, or - for stdin")
    parser.add_argument(
        "--policy",
        default=str(Path(__file__).resolve().parent.parent / "policy" / "access-policy.json"),
        help="path to the policy JSON (defaults to the bundled policy)",
    )
    args = parser.parse_args()

    request = _load_json(args.request)
    policy = _load_json(args.policy)
    if not isinstance(request, dict):
        print("analyze_request: request JSON must be an object", file=sys.stderr)
        return 2
    print(json.dumps(analyze(request, policy), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
