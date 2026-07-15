#!/usr/bin/env python3
"""Fetch 7-day peak metrics for a cluster from the mock Change Gateway.

Usage:
  uv run python scripts/fetch_metrics.py --cluster acme.storefront.checkout.cart --days 7 \
      [--base-url http://localhost:8801]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--base-url", default="http://localhost:8801")
    args = parser.parse_args()

    cluster_path = urllib.parse.quote(args.cluster, safe="")
    url = f"{args.base_url.rstrip('/')}/metrics/{cluster_path}?days={args.days}"
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

    data = json.loads(body)
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
