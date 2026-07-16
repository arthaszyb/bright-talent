"""Read-only scanner over `instances/*`.

Parses instance.yaml, VERSION, .build-info.json, .managed-files.json and
.build-manifest.json (shapes per de-demo/DESIGN.md §S2 — artifacts live at the
instance root, manifest is `{files:[{path,sha256,source}]}`), and computes
per-managed-file drift/conflict status.

Never writes anything. Results are cached in-process, keyed by a cheap mtime
signature so repeat catalog reads don't re-hash the whole tree on every call.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from .config import Config

# Managed files that are literal copies of scaffold/base/<same relative path>
# (per manifest `source: "base"`) can be three-way-compared against the current
# scaffold template directly. Files rendered from a Jinja template
# (`source: "template"`) are instance-specific renders; the scanner does not
# reimplement the builder's templating, so for those it can only do a two-way
# comparison (recorded-sync-hash vs current local hash) — see `_status_for_file`.
BASE_SOURCE = "base"
TEMPLATE_SOURCE = "template"


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return yaml.safe_load(path.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return None


def _tree_signature(path: Path) -> float:
    """Cheap cache-invalidation signature: max mtime across the tree (or 0)."""
    if not path.exists():
        return 0.0
    latest = path.stat().st_mtime
    if path.is_dir():
        for p in path.rglob("*"):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m > latest:
                latest = m
    return latest


def _instance_signature(instance_dir: Path) -> tuple:
    keys = [
        "instance.yaml",
        "VERSION",
        ".build-info.json",
        ".managed-files.json",
        ".build-manifest.json",
        "skills.yaml",
        "skills-lock.json",
    ]
    sig = []
    for k in keys:
        p = instance_dir / k
        sig.append(p.stat().st_mtime if p.is_file() else 0.0)
    sig.append(_tree_signature(instance_dir / "runtime"))
    return tuple(sig)


def _status_for_file(
    recorded_sha: str | None,
    local_sha: str | None,
    scaffold_sha: str | None,
    scaffold_known: bool,
) -> str:
    """Three-way (or, when the scaffold side is unknown, two-way) comparison.

    a = scaffold_sha (current scaffold template hash, if known)
    b = local_sha (current runtime/ file hash)
    c = recorded_sha (.managed-files.json's template_sha256 at last sync)
    """
    if local_sha is None:
        return "missing"
    if scaffold_known:
        a, b, c = scaffold_sha, local_sha, recorded_sha
        if a == c and b == c:
            return "up_to_date"
        if a != c and b == c:
            return "template_moved"
        if a == c and b != c:
            return "local_changed"
        return "both_changed"
    # Scaffold side unknown (templated file) -- two-way only.
    if local_sha == recorded_sha:
        return "up_to_date"
    return "local_changed"


class RepoScanner:
    def __init__(self, config: Config):
        self.config = config
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[tuple, dict]] = {}

    # -- public API -----------------------------------------------------
    def list_instance_ids(self) -> list[str]:
        d = self.config.instances_dir
        if not d.is_dir():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir())

    def scan_instance(self, instance_id: str, force: bool = False) -> dict[str, Any]:
        instance_dir = self.config.instances_dir / instance_id
        sig = _instance_signature(instance_dir)
        with self._lock:
            cached = self._cache.get(instance_id)
            if cached is not None and cached[0] == sig and not force:
                return cached[1]
        result = self._do_scan(instance_id, instance_dir)
        with self._lock:
            self._cache[instance_id] = (sig, result)
        return result

    def scan_all(self, force: bool = False) -> list[dict[str, Any]]:
        return [self.scan_instance(i, force=force) for i in self.list_instance_ids()]

    def current_scaffold_version(self) -> str | None:
        p = self.config.scaffold_dir / "VERSION"
        if not p.is_file():
            return None
        return p.read_text().strip()

    # -- internals --------------------------------------------------------
    def _do_scan(self, instance_id: str, instance_dir: Path) -> dict[str, Any]:
        instance_yaml = _load_yaml(instance_dir / "instance.yaml")
        version_file = instance_dir / "VERSION"
        has_version = version_file.is_file()
        version_text = version_file.read_text().strip() if has_version else None

        build_info = _load_json(instance_dir / ".build-info.json") or {}
        managed = _load_json(instance_dir / ".managed-files.json") or {"files": []}
        manifest = _load_json(instance_dir / ".build-manifest.json") or {"files": []}

        manifest_by_path = {f["path"]: f for f in manifest.get("files", [])}

        managed_files = []
        for m in managed.get("files", []):
            p = m["path"]
            recorded_sha = m.get("template_sha256")
            local_sha = _sha256_file(instance_dir / "runtime" / p)
            manifest_entry = manifest_by_path.get(p)
            source = manifest_entry.get("source") if manifest_entry else None

            scaffold_known = False
            scaffold_sha = None
            if source == BASE_SOURCE:
                scaffold_path = self.config.scaffold_dir / "base" / p
                scaffold_sha = _sha256_file(scaffold_path)
                scaffold_known = scaffold_path.is_file()

            status = _status_for_file(recorded_sha, local_sha, scaffold_sha, scaffold_known)
            managed_files.append({
                "path": p,
                "status": status,
                "source": source,
                "recorded_sha256": recorded_sha,
                "local_sha256": local_sha,
                "scaffold_sha256": scaffold_sha,
                "scaffold_version": m.get("scaffold_version"),
                "synced_at": m.get("synced_at"),
            })

        # Non-managed drift: any other manifest file whose runtime/ hash no
        # longer matches the recorded build manifest hash (build-time drift,
        # separate from the managed-file three-way check above).
        unmanaged_drift = []
        managed_paths = {m["path"] for m in managed_files}
        for f in manifest.get("files", []):
            p = f["path"]
            if p in managed_paths:
                continue
            local_sha = _sha256_file(instance_dir / "runtime" / p)
            if local_sha != f.get("sha256"):
                unmanaged_drift.append({"path": p, "recorded_sha256": f.get("sha256"), "local_sha256": local_sha})

        scaffold_version = self.current_scaffold_version()
        built_scaffold_version = build_info.get("scaffold_version")
        base_status = "unknown"
        if built_scaffold_version and scaffold_version:
            base_status = "stale" if built_scaffold_version != scaffold_version else "current"

        skills_yaml = _load_yaml(instance_dir / "skills.yaml") or {}
        skills_lock = _load_json(instance_dir / "skills-lock.json") or {"skills": {}}
        skills = []
        for name, dep in (skills_yaml.get("dependencies") or {}).items():
            lock = (skills_lock.get("skills") or {}).get(name, {})
            skills.append({
                "name": name,
                "registry": dep.get("registry"),
                "tag": dep.get("tag"),
                "version": lock.get("version"),
                "commit": lock.get("commit"),
                "integrity": lock.get("integrity"),
            })

        return {
            "instance_id": instance_id,
            "path": str(instance_dir),
            "identity": (instance_yaml or {}).get("identity", {}),
            "scope": ((instance_yaml or {}).get("scope") or {}).get("service_catalog", []),
            "files": {
                "instance_yaml": instance_yaml is not None,
                "version": has_version,
            },
            "version": version_text,
            "base": {
                "built_scaffold_version": built_scaffold_version,
                "current_scaffold_version": scaffold_version,
                "status": base_status,
            },
            "build_info": build_info,
            "managed_files": managed_files,
            "unmanaged_drift": unmanaged_drift,
            "skills": skills,
            "scanned_at": time.time(),
        }
