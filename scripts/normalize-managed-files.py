#!/usr/bin/env python3
"""Print .managed-files.json normalized for comparison: the per-build
`synced_at` timestamp is dropped, everything else (paths, hashes, order)
is kept verbatim. Reads the path given as argv[1], or stdin for '-'.

Used by repo-ci to compare committed build metadata against a fresh build
without tripping on the one field that legitimately changes every build.
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    src = sys.stdin if len(sys.argv) < 2 or sys.argv[1] == "-" else open(sys.argv[1])
    data = json.load(src)
    for entry in data.get("files", []):
        entry.pop("synced_at", None)
    json.dump(data, sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
