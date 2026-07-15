"""Shared entrypoint plumbing for `python -m builder.<module> <instance_dir> [...]`."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from builder.errors import BuilderError


def run_entrypoint(func: Callable[[Path, list], int], argv: list[str] | None = None) -> None:
    """Parse `<instance_dir> [extra args...]`, call func(instance_dir, extra_args),
    catch typed BuilderErrors and report them per the S1 contract, then sys.exit.
    """
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m builder.<module> <instance_dir> [args...]", file=sys.stderr)
        sys.exit(2)
    instance_dir = Path(argv[0]).resolve()
    if not instance_dir.is_dir():
        print(f"error: instance directory not found: {instance_dir}", file=sys.stderr)
        sys.exit(2)
    extra = argv[1:]
    try:
        code = func(instance_dir, extra)
    except BuilderError as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - surfaced to CLI, never silent
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code if code is not None else 0)
