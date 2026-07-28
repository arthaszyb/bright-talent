"""Drift detection: compare runtime/ file hashes against .build-manifest.json.

Spec: docs/10-scaffold/design.md §8 / de-cli-spec.md §2.5.
"""

from __future__ import annotations

import json
from pathlib import Path

from builder.build import sha256_file
from builder.errors import BuildError

# Top-level runtime/ directories that hold hook/agent runtime state, not
# build output — they appear only after the agent runs and are never in the
# build manifest (DESIGN.md S3: "work/ (gitignored hook state)"). Excluded
# from drift so `de diff` doesn't false-positive on a session's leftovers.
RUNTIME_STATE_DIRS = frozenset({"work"})


def compute_diff(instance_dir: Path) -> dict:
    manifest_path = instance_dir / ".build-manifest.json"
    if not manifest_path.is_file():
        raise BuildError("no build manifest found — run `de build` first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files", [])
    expected = {e["path"]: e["sha256"] for e in entries}
    # Older manifests predate the executable bit; absent means "unknown", and
    # an unknown must not be reported as a change.
    expected_exec = {e["path"]: e["executable"] for e in entries if "executable" in e}

    runtime_dir = instance_dir / "runtime"
    actual: dict[str, str] = {}
    actual_exec: dict[str, bool] = {}
    if runtime_dir.is_dir():
        for f in sorted(runtime_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(runtime_dir).as_posix()
                if rel.split("/", 1)[0] in RUNTIME_STATE_DIRS:
                    continue
                actual[rel] = sha256_file(f)
                actual_exec[rel] = bool(f.stat().st_mode & 0o111)

    both = set(expected) & set(actual)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    modified = sorted(p for p in both if expected[p] != actual[p])
    # Content-identical but no longer executable (or newly executable): the
    # hash comparison above cannot see this, and for a hook it is the
    # difference between an enforced guardrail and a dead file.
    mode_changed = sorted(
        p for p in both
        if p in expected_exec and p not in modified and expected_exec[p] != actual_exec[p]
    )

    return {"missing": missing, "extra": extra, "modified": modified, "mode_changed": mode_changed}


def main(instance_dir: Path, extra: list[str]) -> int:
    result = compute_diff(instance_dir)
    if not any(result[k] for k in ("missing", "extra", "modified", "mode_changed")):
        print("no drift: runtime/ matches the last build manifest.")
        return 0

    if result["modified"]:
        print("modified:")
        for p in result["modified"]:
            print(f"  - {p}")
    if result["mode_changed"]:
        print("permissions changed:")
        for p in result["mode_changed"]:
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
