"""JSON report writer shared by every subcommand (--report <path>)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_report(path: Path | None, data: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
