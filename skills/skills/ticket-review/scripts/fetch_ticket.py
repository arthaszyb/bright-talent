#!/usr/bin/env python3
"""Fetch a ticket from the mock Change Gateway and print it as JSON.

Usage:
  uv run python scripts/fetch_ticket.py --ticket-id 1002 [--base-url http://localhost:8801]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8801")
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/tickets/{args.ticket_id}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        print(json.dumps({"error": f"HTTP {exc.code} fetching {url}"}), file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(json.dumps({"error": f"could not reach {url}: {exc.reason}"}), file=sys.stderr)
        return 1

    if status != 200:
        print(json.dumps({"error": f"HTTP {status} fetching {url}"}), file=sys.stderr)
        return 1

    # Pass through: validate it's JSON, then print compactly to stdout.
    data = json.loads(body)
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
