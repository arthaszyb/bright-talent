#!/usr/bin/env python3
"""Mock Change Gateway API for the ticket-review demo skill.

Stdlib-only HTTP server. Serves three endpoints against deterministic,
hand-seeded fixture data (no randomness, no external calls):

  GET  /tickets/{id}                  -> ticket JSON
  GET  /metrics/{cluster}?days=7      -> synthetic 7-day peak metrics
  POST /tickets/{id}/comments         -> echoes the accepted comment

Seeded tickets:
  1001 - safe: scale-up, replicas stay at 3, no campaign conflict
  1002 - SOP-violating: scale-down that drops replicas below the minimum of 2
  1003 - borderline: post-change predicted utilization sits near the 80% line

Run:
  uv run python scripts/mock_server.py [--port 8801]
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Seed data (deterministic; invented round numbers for illustration only).
# ---------------------------------------------------------------------------

TICKETS: dict[str, dict] = {
    "1001": {
        "ticket_id": "1001",
        "title": "Scale up cache cluster acme-checkout-sessions",
        "cluster": "acme.storefront.checkout.sessions",
        "change_type": "scale_up",
        "requested_by": "mentor-one@acme.example",
        "current": {"replicas": 3, "mem_per_node_gb": 8, "nodes": 6},
        "target": {"replicas": 3, "mem_per_node_gb": 8, "nodes": 9},
        "apply_reason": "Sustained memory pressure ahead of a planned promotion event.",
        "recent_campaign_window": None,
        "status": "pending_review",
    },
    "1002": {
        "ticket_id": "1002",
        "title": "Scale down cache cluster acme-checkout-cart",
        "cluster": "acme.storefront.checkout.cart",
        "change_type": "scale_down",
        "requested_by": "mentor-two@acme.example",
        "current": {"replicas": 2, "mem_per_node_gb": 8, "nodes": 4},
        "target": {"replicas": 1, "mem_per_node_gb": 8, "nodes": 4},
        "apply_reason": "Utilization has looked low this week, requesting smaller footprint.",
        "recent_campaign_window": {
            "name": "mid-year-flash-sale",
            "ends_days_ago": 2,
        },
        "status": "pending_review",
    },
    "1003": {
        "ticket_id": "1003",
        "title": "Scale up cache cluster acme-storefront-search-cache",
        "cluster": "acme.storefront.search.cache",
        "change_type": "scale_up",
        "requested_by": "mentor-one@acme.example",
        "current": {"replicas": 2, "mem_per_node_gb": 16, "nodes": 5},
        "target": {"replicas": 2, "mem_per_node_gb": 16, "nodes": 6},
        "apply_reason": "Query volume trending up ahead of a regional expansion; only one extra node approved this quarter.",
        "recent_campaign_window": None,
        "status": "pending_review",
    },
}

# 7-day peak metrics per cluster. mem_util_peak_pct is the observed peak
# memory utilization on the *current* topology over the trailing 7 days.
METRICS: dict[str, dict] = {
    "acme.storefront.checkout.sessions": {
        "cluster": "acme.storefront.checkout.sessions",
        "days": 7,
        "mem_util_peak_pct": 82.0,
        "cpu_util_peak_pct": 55.0,
        "qps_peak": 42000,
    },
    "acme.storefront.checkout.cart": {
        "cluster": "acme.storefront.checkout.cart",
        "days": 7,
        "mem_util_peak_pct": 35.0,
        "cpu_util_peak_pct": 20.0,
        "qps_peak": 9000,
    },
    "acme.storefront.search.cache": {
        "cluster": "acme.storefront.search.cache",
        "days": 7,
        "mem_util_peak_pct": 88.0,
        "cpu_util_peak_pct": 48.0,
        "qps_peak": 31000,
    },
}

COMMENTS: dict[str, list[dict]] = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "TicketReviewMock/0.1"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # quieter default logging
        pass

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]

        if len(parts) == 2 and parts[0] == "tickets":
            ticket = TICKETS.get(parts[1])
            if ticket is None:
                self._send_json(404, {"error": f"ticket {parts[1]} not found"})
                return
            self._send_json(200, ticket)
            return

        if len(parts) == 2 and parts[0] == "metrics":
            cluster = parts[1]
            metrics = METRICS.get(cluster)
            if metrics is None:
                self._send_json(404, {"error": f"no metrics for cluster {cluster}"})
                return
            days = parse_qs(parsed.query).get("days", ["7"])[0]
            result = dict(metrics)
            result["days"] = int(days)
            self._send_json(200, result)
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]

        if len(parts) == 3 and parts[0] == "tickets" and parts[2] == "comments":
            ticket_id = parts[1]
            if ticket_id not in TICKETS:
                self._send_json(404, {"error": f"ticket {ticket_id} not found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            COMMENTS.setdefault(ticket_id, []).append(payload)
            self._send_json(
                201,
                {
                    "ticket_id": ticket_id,
                    "accepted": True,
                    "comment": payload,
                },
            )
            return

        self._send_json(404, {"error": "not found"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8801)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"ticket-review mock server listening on http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
