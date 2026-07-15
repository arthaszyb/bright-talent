"""Base version upgrade (comment-preserving text surgery on instance.yaml) —
not implemented in this demo wave.

See docs/10-scaffold/design.md §7 and de-cli-spec.md §2.8.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(instance_dir: Path, extra: list[str]) -> int:
    print(
        "error: `de upgrade` is not implemented in this demo wave; "
        "see docs/10-scaffold/design.md §7.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
