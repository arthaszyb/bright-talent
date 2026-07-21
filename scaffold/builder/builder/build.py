"""14-phase build pipeline (docs/10-scaffold/design.md §3).

Composes `<instance>/runtime/` (and a best-effort `<instance>/editor/`) from
scaffold `base/` + `templates/` + the instance's own `instance.yaml`/`kb/`.

Build artifacts are written at the **instance root** (this task's Deliverable 1
S2 contract): `.build-manifest.json`, `.build-info.json`, `.managed-files.json`.
(DESIGN.md's S2 text nests the first two under `runtime/`; the task brief for
this wave pins all three to the instance root — resolved in favor of the
explicit wave brief, noted in the final report.)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from builder import merge, render, validate
from builder import skills as skills_mod
from builder.errors import BuildError

SCAFFOLD_VERSION_FILE = "VERSION"


def resolve_scaffold_root(instance_dir: Path) -> Path:
    env = os.environ.get("DE_SCAFFOLD_ROOT")
    if env:
        return Path(env).resolve()
    candidate = (instance_dir / ".." / ".." / "scaffold").resolve()
    if candidate.is_dir():
        return candidate
    raise BuildError(
        "could not resolve scaffold root: set DE_SCAFFOLD_ROOT or place the instance "
        "under <scaffold>/../../instances/<name>"
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_files(dir_path: Path, prefix: str) -> dict[str, Path]:
    """relative-runtime-path (posix, prefixed) -> absolute source path."""
    result: dict[str, Path] = {}
    if not dir_path.is_dir():
        return result
    for f in sorted(dir_path.rglob("*")):
        if f.is_file():
            rel = f"{prefix}/{f.relative_to(dir_path).as_posix()}"
            result[rel] = f
    return result


def merge_with_sources(
    base_map: dict[str, Path], overlay_map: dict[str, Path], overlay_label: str
) -> dict[str, tuple[Path, str]]:
    merged = merge.merge_directory_map(
        {k: str(v) for k, v in base_map.items()},
        {k: str(v) for k, v in overlay_map.items()},
        overlay_label,
    )
    out: dict[str, tuple[Path, str]] = {}
    for rel, path_str in merged.items():
        source = "instance" if rel in overlay_map else "base"
        out[rel] = (Path(path_str), source)
    return out


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _claude_cli_version() -> str | None:
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip() or out.stderr.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def build_runtime(instance_dir: Path, scaffold_root: Path, config: dict) -> dict:
    """Runs phases 3-14 against runtime/. Returns dict with manifest_entries,
    managed_entries, skills list — used by callers/tests."""
    base_root = scaffold_root / "base"
    templates_dir = scaffold_root / "templates"
    runtime_dir = instance_dir / "runtime"

    # Phase 3: clean runtime/
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True)

    manifest_entries: list[dict] = []
    managed_entries: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    scaffold_version = (scaffold_root / SCAFFOLD_VERSION_FILE).read_text(encoding="utf-8").strip() \
        if (scaffold_root / SCAFFOLD_VERSION_FILE).is_file() else "0.0.0"

    def emit(rel: str, dst: Path, source: str, managed: bool) -> None:
        digest = sha256_file(dst)
        manifest_entries.append({"path": rel, "sha256": digest, "source": source})
        if managed:
            managed_entries.append(
                {
                    "path": rel,
                    "template_sha256": digest,
                    "synced_at": now_iso,
                    "scaffold_version": scaffold_version,
                }
            )

    # Phases 4-6: copy base .claude/ (hooks/policy/tools), merge instance kb/ into base kb/
    base_claude_map = collect_files(base_root / ".claude", ".claude")
    base_kb_map = collect_files(base_root / "kb", "kb")
    instance_kb_map = collect_files(instance_dir / "kb", "kb")

    kb_merged = merge_with_sources(base_kb_map, instance_kb_map, "instance kb/")

    for rel, src in base_claude_map.items():
        dst = runtime_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if os.access(src, os.X_OK):
            dst.chmod(dst.stat().st_mode | 0o111)
        emit(rel, dst, "base", managed=True)

    for rel, (src, source) in kb_merged.items():
        dst = runtime_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        emit(rel, dst, source, managed=(source == "base"))

    # Phase 12 (done early so CLAUDE.md can list skills): install skills
    skills_list, skill_manifest_entries, _warnings = skills_mod.resolve_and_install(
        instance_dir, runtime_dir
    )
    for entry in skill_manifest_entries:
        manifest_entries.append(entry)  # source="instance", not managed

    # Phase 7: render CLAUDE.md
    jenv = render.get_jinja_env(templates_dir)
    identity = config["identity"]
    scope = config["scope"]
    escalation = config.get("escalation") or {}
    mentor_emails = escalation.get("mentor_emails") or []
    claude_md_cfg = config.get("claude_md") or {}
    policy_summary = render.build_policy_summary(base_root / ".claude" / "policy")

    claude_md_text = render.render_claude_md(
        jenv,
        {
            "identity": identity,
            "scope": scope,
            "mentor_emails": mentor_emails,
            "policy_summary": policy_summary,
            "skills": skills_list,
            "extra_rules": claude_md_cfg.get("extra_rules", ""),
        },
    )
    claude_md_path = runtime_dir / "CLAUDE.md"
    claude_md_path.write_text(claude_md_text, encoding="utf-8")
    emit("CLAUDE.md", claude_md_path, "template", managed=True)

    # Phase 8: merge + render settings.json (monotonic default_mode, additive
    # permissions, immutable base env keys)
    settings_cfg = (config.get("settings") or {}).get("permissions") or {}
    requested_mode = settings_cfg.get("default_mode")
    effective_mode = merge.check_monotonic_mode(requested_mode)
    env_overlay = (config.get("settings") or {}).get("env") or {}
    merge.check_env_immutable(env_overlay)

    settings_text = render.render_settings_json(
        jenv,
        {
            "default_mode": effective_mode,
            "extra_allow": settings_cfg.get("extra_allow") or [],
            "extra_deny": settings_cfg.get("extra_deny") or [],
            "extra_ask": settings_cfg.get("extra_ask") or [],
            "env_vars": env_overlay,
        },
    )
    settings_path = runtime_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(settings_text, encoding="utf-8")
    emit(".claude/settings.json", settings_path, "template", managed=True)

    # Phase 9: merge + render .mcp.json (protected servers undisableable)
    mcp_cfg = config.get("mcp") or {}
    mcp_text = render.render_mcp_json(jenv, {"extra_servers": mcp_cfg.get("extra_servers") or {}})
    mcp_data = json.loads(mcp_text)
    to_disable = set(merge.merge_disable_servers(mcp_cfg.get("disable_servers") or []))
    for name in to_disable:
        mcp_data["mcpServers"].pop(name, None)
    enable_extra = mcp_cfg.get("enable_project_servers") or []
    enabled = mcp_data.get("enabledMcpjsonServers", [])
    for name in enable_extra:
        if name not in enabled:
            enabled.append(name)
    mcp_data["enabledMcpjsonServers"] = enabled
    mcp_path = runtime_dir / ".mcp.json"
    _write_json(mcp_path, mcp_data)
    emit(".mcp.json", mcp_path, "template", managed=True)

    # Phase 11: render bridge config if enabled
    bridge_cfg = config.get("bridge") or {}
    if bridge_cfg.get("enabled"):
        bridge_text = render.render_bridge_yaml(
            jenv, {"bridge": bridge_cfg, "env": dict(os.environ)}
        )
        log_dir = instance_dir / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        bridge_path = log_dir / "bridge-config.yaml"
        bridge_path.write_text(bridge_text, encoding="utf-8")

    # Phase 13: seed instance tests fresh every build
    seeds_dir = scaffold_root / "instance-test-seeds"
    tests_dir = runtime_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    for seed in sorted(seeds_dir.glob("*.mock.yaml")):
        dst = tests_dir / seed.name
        shutil.copy2(seed, dst)
        emit(f"tests/{seed.name}", dst, "seed", managed=True)

    # work/ and log/ dirs
    (runtime_dir / "work").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "log").mkdir(parents=True, exist_ok=True)

    return {
        "manifest_entries": manifest_entries,
        "managed_entries": managed_entries,
        "skills": skills_list,
        "scaffold_version": scaffold_version,
        "now_iso": now_iso,
    }


def build_editor(instance_dir: Path, scaffold_root: Path, config: dict) -> None:
    """Best-effort restricted editor/ build (de edit). Non-fatal on failure."""
    templates_dir = scaffold_root / "templates"
    editor_dir = instance_dir / "editor"
    if editor_dir.exists():
        shutil.rmtree(editor_dir)
    editor_dir.mkdir(parents=True)
    jenv = render.get_jinja_env(templates_dir)
    claude_md_text = render.render_editor_claude_md(jenv, {"identity": config["identity"]})
    (editor_dir / "CLAUDE.md").write_text(claude_md_text, encoding="utf-8")
    settings_text = render.render_editor_settings_json(jenv, {})
    claude_dir = editor_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "settings.json").write_text(settings_text, encoding="utf-8")


def run_build(instance_dir: Path) -> None:
    # Phase 1: validate
    config = validate.load_and_validate(instance_dir)
    # Phase 2: load instance config / scaffold root
    scaffold_root = resolve_scaffold_root(instance_dir)

    result = build_runtime(instance_dir, scaffold_root, config)

    # Phase 14: write manifest + build-info + managed-files (instance root, per S2)
    manifest_path = instance_dir / ".build-manifest.json"
    _write_json(manifest_path, {"files": result["manifest_entries"]})

    build_info_path = instance_dir / ".build-info.json"
    _write_json(
        build_info_path,
        {
            "scaffold_version": result["scaffold_version"],
            "built_at": result["now_iso"],
            "claude_cli_version": _claude_cli_version(),
            "instance_identity": config["identity"]["id"],
        },
    )

    managed_files_path = instance_dir / ".managed-files.json"
    _write_json(managed_files_path, {"files": result["managed_entries"]})

    try:
        build_editor(instance_dir, scaffold_root, config)
    except Exception as e:  # noqa: BLE001 - editor build is best-effort
        print(f"warning: editor/ build failed (non-fatal): {e}", file=sys.stderr)


def main(instance_dir: Path, extra: list[str]) -> int:
    run_build(instance_dir)
    print(f"build complete: {instance_dir / 'runtime'}")
    return 0


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
