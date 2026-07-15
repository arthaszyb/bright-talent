"""Drift detection: compare runtime/ file hashes against .build-manifest.json.

Spec: docs/10-scaffold/design.md §8 / de-cli-spec.md §2.5.
"""

from __future__ import annotations

import json
from pathlib import Path

from builder.build import sha256_file
from builder.errors import BuildError


def compute_diff(instance_dir: Path) -> dict:
    manifest_path = instance_dir / ".build-manifest.json"
    if not manifest_path.is_file():
        raise BuildError("no build manifest found — run `de build` first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {e["path"]: e["sha256"] for e in manifest.get("files", [])}

    runtime_dir = instance_dir / "runtime"
    actual: dict[str, str] = {}
    if runtime_dir.is_dir():
        for f in sorted(runtime_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(runtime_dir).as_posix()
                actual[rel] = sha256_file(f)

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    modified = sorted(p for p in (set(expected) & set(actual)) if expected[p] != actual[p])

    return {"missing": missing, "extra": extra, "modified": modified}


def main(instance_dir: Path, extra: list[str]) -> int:
    result = compute_diff(instance_dir)
    if not result["missing"] and not result["extra"] and not result["modified"]:
        print("no drift: runtime/ matches the last build manifest.")
        return 0

    if result["modified"]:
        print("modified:")
        for p in result["modified"]:
            print(f"  - {p}")
    if result["missing"]:
        print("missing:")
        for p in result["missing"]:
            print(f"  - {p}")
    if result["extra"]:
        print("extra:")
        for p in result["extra"]:
            print(f"  - {p}")
    return 1


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
