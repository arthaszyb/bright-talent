#!/usr/bin/env python3
"""Apply the cache-scaling SOP rules to a ticket + its 7-day peak metrics.

Reads ticket JSON and metrics JSON (each from a file path, or from stdin if
the path argument is omitted / "-"), applies three illustrative SOP rules,
and prints a single JSON object to stdout:

  {
    "ticket_id": ...,
    "cluster": ...,
    "predicted_mem_util_pct": ...,
    "checks": [
      {"rule": "...", "status": "pass|warn|fail", "evidence": "..."},
      ...
    ],
    "summary": "pass|warn|fail"   # worst status across all checks
  }

SOP rules (illustrative; see kb/team/runbooks/cache-scaling-sop.md for the human-
readable version):
  R1  post-change predicted peak memory utilization must stay < 80%
  R2  replica count >= 2 after the change
  R3  scale-down is forbidden within 7 days of a traffic campaign ending

Usage:
  uv run python scripts/analyze.py --ticket /tmp/t.json --metrics /tmp/m.json
  cat ticket.json | uv run python scripts/analyze.py --ticket - --metrics /tmp/m.json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

MEM_UTIL_FAIL_THRESHOLD_PCT = 80.0
MIN_REPLICAS = 2
CAMPAIGN_COOLDOWN_DAYS = 7


def _load(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _worst(statuses: list[str]) -> str:
    order = {"pass": 0, "warn": 1, "fail": 2}
    return max(statuses, key=lambda s: order.get(s, 0)) if statuses else "pass"


def check_predicted_utilization(ticket: dict, metrics: dict) -> tuple[dict, float]:
    """R1: predicted post-change peak memory utilization must stay < 80%."""
    current = ticket["current"]
    target = ticket["target"]

    current_nodes = current["nodes"]
    current_mem_per_node = current["mem_per_node_gb"]
    target_nodes = target["nodes"]
    target_mem_per_node = target["mem_per_node_gb"]

    current_capacity_gb = current_nodes * current_mem_per_node
    target_capacity_gb = target_nodes * target_mem_per_node

    peak_util_pct = metrics["mem_util_peak_pct"]
    # Absolute memory used at peak, held constant, redistributed over new capacity.
    used_gb = current_capacity_gb * (peak_util_pct / 100.0)
    predicted_util_pct = (used_gb / target_capacity_gb) * 100.0 if target_capacity_gb else float("inf")

    if predicted_util_pct >= MEM_UTIL_FAIL_THRESHOLD_PCT:
        status = "fail"
    elif predicted_util_pct >= MEM_UTIL_FAIL_THRESHOLD_PCT - 10:
        status = "warn"
    else:
        status = "pass"

    evidence = (
        f"7d observed peak={peak_util_pct:.1f}% on current capacity="
        f"{current_capacity_gb:.0f}GB ({current_nodes} nodes x {current_mem_per_node}GB); "
        f"target capacity={target_capacity_gb:.0f}GB ({target_nodes} nodes x {target_mem_per_node}GB); "
        f"predicted post-change peak={predicted_util_pct:.1f}% "
        f"(threshold < {MEM_UTIL_FAIL_THRESHOLD_PCT:.0f}%)"
    )
    return (
        {
            "rule": "predicted_peak_memory_utilization_below_80pct",
            "status": status,
            "evidence": evidence,
        },
        predicted_util_pct,
    )


def check_min_replicas(ticket: dict) -> dict:
    """R2: replica count >= 2 after the change."""
    target_replicas = ticket["target"]["replicas"]
    status = "pass" if target_replicas >= MIN_REPLICAS else "fail"
    evidence = (
        f"target replicas={target_replicas} (minimum required={MIN_REPLICAS})"
    )
    return {
        "rule": "minimum_replica_count",
        "status": status,
        "evidence": evidence,
    }


def check_campaign_cooldown(ticket: dict) -> dict:
    """R3: scale-down forbidden within 7 days of a traffic campaign ending."""
    if ticket["change_type"] != "scale_down":
        return {
            "rule": "campaign_cooldown_for_scale_down",
            "status": "pass",
            "evidence": "not a scale-down change; rule not applicable",
        }

    window = ticket.get("recent_campaign_window")
    if not window:
        return {
            "rule": "campaign_cooldown_for_scale_down",
            "status": "pass",
            "evidence": "no recent traffic campaign recorded for this cluster",
        }

    ends_days_ago = window["ends_days_ago"]
    if ends_days_ago < CAMPAIGN_COOLDOWN_DAYS:
        status = "fail"
    else:
        status = "pass"
    evidence = (
        f"scale-down requested {ends_days_ago} day(s) after campaign "
        f"'{window['name']}' ended (cooldown={CAMPAIGN_COOLDOWN_DAYS} days)"
    )
    return {
        "rule": "campaign_cooldown_for_scale_down",
        "status": status,
        "evidence": evidence,
    }


def analyze(ticket: dict, metrics: dict) -> dict:
    util_check, predicted_util_pct = check_predicted_utilization(ticket, metrics)
    replica_check = check_min_replicas(ticket)
    campaign_check = check_campaign_cooldown(ticket)

    checks = [util_check, replica_check, campaign_check]
    summary = _worst([c["status"] for c in checks])

    return {
        "ticket_id": ticket["ticket_id"],
        "cluster": ticket["cluster"],
        "change_type": ticket["change_type"],
        "predicted_mem_util_pct": round(predicted_util_pct, 1),
        "checks": checks,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", required=True, help="path to ticket JSON, or - for stdin")
    parser.add_argument("--metrics", required=True, help="path to metrics JSON, or - for stdin")
    args = parser.parse_args()

    if args.ticket == "-" and args.metrics == "-":
        parser.error("only one of --ticket/--metrics may be '-' (stdin)")

    ticket = _load(args.ticket)
    metrics = _load(args.metrics)

    result = analyze(ticket, metrics)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
