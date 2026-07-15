"""Git tag release workflow — not implemented in this demo wave.

See de-cli-spec.md §2.10.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(instance_dir: Path, extra: list[str]) -> int:
    print(
        "error: `de release` is not implemented in this demo wave; "
        "see docs/10-scaffold/de-cli-spec.md §2.10.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
