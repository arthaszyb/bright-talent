#!/usr/bin/env python3
"""Render the final Markdown review comment from analyze.py output.

Reads the analyze-stage JSON (file path, or stdin if omitted / "-") and
prints a fixed-structure Markdown comment:

  ## Summary
  ## Review Comment
  ### Checks
  ### Verified Inputs
  ### Concerns

The comment never contains an approve/reject verdict — only pass/warn/fail
findings for a human to act on.

Usage:
  uv run python scripts/render_comment.py --analysis /tmp/a.json
  uv run python scripts/analyze.py ... | uv run python scripts/render_comment.py --analysis -
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

STATUS_ICON = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}


def _load(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def render(analysis: dict) -> str:
    ticket_id = analysis["ticket_id"]
    cluster = analysis["cluster"]
    change_type = analysis["change_type"]
    summary = analysis["summary"]
    predicted_util = analysis["predicted_mem_util_pct"]
    checks = analysis["checks"]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"Ticket **{ticket_id}** ({change_type}) on cluster `{cluster}` — "
        f"overall SOP result: **{summary.upper()}**. Predicted post-change "
        f"peak memory utilization: **{predicted_util:.1f}%**."
    )
    lines.append("")
    lines.append("## Review Comment")
    lines.append("")
    lines.append(
        "This is an automated SOP check only. It does **not** approve or "
        "reject this ticket — a human reviewer makes the final decision."
    )
    lines.append("")

    lines.append("### Checks")
    lines.append("")
    lines.append("| Rule | Status | Evidence |")
    lines.append("|---|---|---|")
    for check in checks:
        icon = STATUS_ICON.get(check["status"], check["status"].upper())
        evidence = check["evidence"].replace("|", "\\|")
        lines.append(f"| {check['rule']} | {icon} | {evidence} |")
    lines.append("")

    lines.append("### Verified Inputs")
    lines.append("")
    lines.append(f"- Ticket ID: `{ticket_id}`")
    lines.append(f"- Cluster: `{cluster}`")
    lines.append(f"- Change type: `{change_type}`")
    lines.append("- Metrics window: 7-day peak (mock Change Gateway)")
    lines.append(f"- Generated: {generated_at}")
    lines.append("")

    lines.append("### Concerns")
    lines.append("")
    failing = [c for c in checks if c["status"] == "fail"]
    warning = [c for c in checks if c["status"] == "warn"]
    if not failing and not warning:
        lines.append("- None. All SOP checks passed.")
    else:
        for check in failing:
            lines.append(f"- **FAIL** ({check['rule']}): {check['evidence']}")
        for check in warning:
            lines.append(f"- **WARN** ({check['rule']}): {check['evidence']}")
    lines.append("")
    lines.append(
        "_No approve/reject action was taken. Route this comment to the "
        "ticket for human decision._"
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, help="path to analyze.py output JSON, or - for stdin")
    args = parser.parse_args()

    analysis = _load(args.analysis)
    print(render(analysis), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
