"""Small YAML/TOML loading helpers shared across subcommands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


class UsageError(Exception):
    """Bad input (missing file, unparseable YAML, malformed fixture, ...).

    Raised for conditions that should surface as `de-eval`'s usage exit (2)
    -- as opposed to a normal test failure (exit 1).
    """


def load_yaml(path: Path) -> Any:
    if not path.is_file():
        raise UsageError(f"file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise UsageError(f"invalid YAML in {path}: {e}") from e


def load_toml(path: Path) -> dict:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
        import tomli as tomllib  # type: ignore[no-redef]
    if not path.is_file():
        raise UsageError(f"file not found: {path}")
    with open(path, "rb") as f:
        return tomllib.load(f)


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)
