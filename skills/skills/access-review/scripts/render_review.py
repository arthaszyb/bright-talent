#!/usr/bin/env python3
"""Render the access-review analysis JSON into a Markdown review comment.

Reads analyze_request.py output (from a file path, or stdin if omitted / "-")
and prints a structured Markdown comment with these sections:

  ## Summary
  ## Review Comment
  ### Checks
  ### Verified Inputs
  ### Concerns

This comment is advisory only: it never grants, revokes, or approves access —
that decision stays with a human access approver.

Usage:
  uv run python scripts/render_review.py --analysis /tmp/analysis.json
  cat analysis.json | uv run python scripts/render_review.py --analysis -
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

STATUS_LABEL = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}


def render(analysis: dict, generated_at: str) -> str:
    request_id = analysis.get("request_id")
    requestor = analysis.get("requestor")
    service = analysis.get("service")
    role = analysis.get("role")
    environment = analysis.get("environment")
    summary = analysis.get("summary", "pass")
    checks = analysis.get("checks", [])

    lines: list[str] = []
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"Access request **{request_id}** — `{role}` on `{service}` "
        f"({environment}) for {requestor} — overall policy result: "
        f"**{STATUS_LABEL.get(summary, summary.upper())}**."
    )
    lines.append("")
    lines.append("## Review Comment")
    lines.append("")
    lines.append(
        "This is an automated least-privilege policy check only. It does "
        "**not** grant, revoke, or approve access — a human access approver "
        "makes the final decision."
    )
    lines.append("")
    lines.append("### Checks")
    lines.append("")
    lines.append("| Rule | Status | Evidence |")
    lines.append("|---|---|---|")
    for c in checks:
        lines.append(
            f"| {c.get('rule')} | {STATUS_LABEL.get(c.get('status'), str(c.get('status')).upper())} "
            f"| {c.get('evidence')} |"
        )
    lines.append("")
    lines.append("### Verified Inputs")
    lines.append("")
    lines.append(f"- Request ID: `{request_id}`")
    lines.append(f"- Requestor: `{requestor}`")
    lines.append(f"- Service: `{service}`")
    lines.append(f"- Role: `{role}`")
    lines.append(f"- Environment: `{environment}`")
    lines.append(f"- Generated: {generated_at}")
    lines.append("")
    lines.append("### Concerns")
    lines.append("")
    concerns = [c for c in checks if c.get("status") in ("fail", "warn")]
    if concerns:
        for c in concerns:
            lines.append(
                f"- **{STATUS_LABEL.get(c.get('status'), str(c.get('status')).upper())}** "
                f"({c.get('rule')}): {c.get('evidence')}"
            )
    else:
        lines.append("- None. All policy checks passed.")
    lines.append("")
    lines.append(
        "_No grant/revoke action was taken. Route this comment to the access "
        "request for human decision._"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", default="-", help="path to analyze_request.py output JSON, or - for stdin")
    parser.add_argument(
        "--now",
        default=None,
        help="override the generation timestamp (YYYY-MM-DD HH:MM UTC) for reproducible output",
    )
    args = parser.parse_args()

    if args.analysis in ("-", None):
        analysis = json.load(sys.stdin)
    else:
        from pathlib import Path

        analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))

    generated_at = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(render(analysis, generated_at))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
