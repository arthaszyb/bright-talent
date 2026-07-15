"""Bridge service lifecycle — not implemented in this demo wave.

See docs/10-scaffold/design.md §2 (`bridge.py`) and DESIGN.md S6 for the full
contract; `bridge/` (M5) will implement the actual FastAPI service.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(instance_dir: Path, extra: list[str]) -> int:
    print(
        "error: bridge lifecycle management is not implemented in this demo wave; "
        "see docs/10-scaffold/design.md §2 and bridge/ (milestone M5).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
