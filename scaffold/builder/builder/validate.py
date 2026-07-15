"""instance.yaml (schema v1) field-level validation.

Spec: docs/10-scaffold/instance-yaml-spec.md. Accumulates every error found
(does not stop at first failure) and raises a single ValidationError whose
message is a bulleted list, each line naming the offending field.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from builder.errors import ValidationError

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PERMISSION_MODES = ("plan", "default", "acceptEdits", "bypassPermissions")
TOP_LEVEL_KEYS = {
    "schema_version",
    "identity",
    "scope",
    "base",
    "layers",
    "settings",
    "mcp",
    "escalation",
    "claude_md",
    "kb",
    "bridge",
    "advanced",
}
REQUIRED_TOP_LEVEL = ("schema_version", "identity", "scope", "base")


def _is_nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _errs_settings(settings: Any, errors: list[str], prefix: str = "settings") -> None:
    if settings is None:
        return
    if not isinstance(settings, dict):
        errors.append(f"{prefix}: must be a mapping")
        return
    if "sandbox" in settings:
        errors.append(f"{prefix}.sandbox is deprecated and no longer supported")
    perms = settings.get("permissions")
    if perms is not None:
        if not isinstance(perms, dict):
            errors.append(f"{prefix}.permissions: must be a mapping")
        else:
            for key in ("extra_allow", "extra_deny", "extra_ask"):
                val = perms.get(key, [])
                if not isinstance(val, list) or not all(isinstance(x, str) and x for x in val):
                    errors.append(f"{prefix}.permissions.{key}: must be a list of non-empty strings")
            mode = perms.get("default_mode")
            if mode is not None and mode not in PERMISSION_MODES:
                errors.append(
                    f"{prefix}.permissions.default_mode: '{mode}' is not one of {list(PERMISSION_MODES)}"
                )
    env = settings.get("env")
    if env is not None:
        if not isinstance(env, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in env.items()
        ):
            errors.append(f"{prefix}.env: must be a mapping of string to string")
    hooks = settings.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        errors.append(f"{prefix}.hooks: must be a mapping")


def _errs_mcp(mcp: Any, errors: list[str]) -> None:
    if mcp is None:
        return
    if not isinstance(mcp, dict):
        errors.append("mcp: must be a mapping")
        return
    if "extra_servers" in mcp and not isinstance(mcp["extra_servers"], dict):
        errors.append("mcp.extra_servers: must be a mapping")
    for key in ("enable_project_servers", "disable_servers"):
        if key in mcp:
            val = mcp[key]
            if not isinstance(val, list) or not all(isinstance(x, str) and x for x in val):
                errors.append(f"mcp.{key}: must be a list of non-empty strings")


def _errs_escalation(esc: Any, errors: list[str]) -> None:
    if esc is None:
        return
    if not isinstance(esc, dict):
        errors.append("escalation: must be a mapping")
        return
    if "enabled" in esc and not isinstance(esc["enabled"], bool):
        errors.append("escalation.enabled: must be a boolean")
    emails = esc.get("mentor_emails", [])
    if not isinstance(emails, list):
        errors.append("escalation.mentor_emails: must be a list")
    else:
        for e in emails:
            if not isinstance(e, str) or not EMAIL_RE.match(e):
                errors.append(f"escalation.mentor_emails: invalid email '{e}'")
    if "show_event_id" in esc and not isinstance(esc["show_event_id"], bool):
        errors.append("escalation.show_event_id: must be a boolean")
    if "event_store" in esc and not _is_nonempty_str(esc["event_store"]):
        errors.append("escalation.event_store: must be a non-empty string")
    dedup = esc.get("dedup_window_seconds")
    if dedup is not None and (not isinstance(dedup, int) or isinstance(dedup, bool) or dedup < 0):
        errors.append("escalation.dedup_window_seconds: must be an integer >= 0")
    guard = esc.get("guard")
    if guard is not None:
        if not isinstance(guard, dict):
            errors.append("escalation.guard: must be a mapping")
        else:
            if "enabled" in guard and not isinstance(guard["enabled"], bool):
                errors.append("escalation.guard.enabled: must be a boolean")
            for key in ("max_tool_failures", "max_repeated_attempts"):
                val = guard.get(key)
                if val is not None and (not isinstance(val, int) or isinstance(val, bool) or val < 1):
                    errors.append(f"escalation.guard.{key}: must be an integer >= 1")


def _errs_kb(kb: Any, errors: list[str]) -> None:
    if kb is None:
        return
    if not isinstance(kb, dict):
        errors.append("kb: must be a mapping")
        return
    if "team_index" in kb and not _is_nonempty_str(kb["team_index"]):
        errors.append("kb.team_index: must be a non-empty string")
    refs = kb.get("live_refs", [])
    if not isinstance(refs, list):
        errors.append("kb.live_refs: must be a list")
        return
    names = set()
    kb_root_dests = 0
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"kb.live_refs[{i}]: must be a mapping")
            continue
        name = ref.get("name")
        if not _is_nonempty_str(name):
            errors.append(f"kb.live_refs[{i}].name: must be a non-empty string")
        elif name in names:
            errors.append(f"kb.live_refs[{i}].name: duplicate name '{name}'")
        else:
            names.add(name)
        if not ref.get("repo") and not ref.get("src"):
            errors.append(f"kb.live_refs[{i}]: at least one of 'repo' or 'src' is required")
        dest = ref.get("dest") or (f"kb/{name}" if name else None)
        if dest == "kb":
            kb_root_dests += 1
    if kb_root_dests > 1:
        errors.append("kb.live_refs: at most one entry may resolve to dest: kb (wiki-root mode)")


def _errs_bridge(bridge: Any, errors: list[str]) -> None:
    if bridge is None:
        return
    if not isinstance(bridge, dict):
        errors.append("bridge: must be a mapping")
        return
    enabled = bridge.get("enabled", False)
    if "enabled" in bridge and not isinstance(enabled, bool):
        errors.append("bridge.enabled: must be a boolean")
    for str_field in ("repo", "version"):
        if str_field in bridge and bridge[str_field] is not None and not isinstance(bridge[str_field], str):
            errors.append(f"bridge.{str_field}: must be a string")
    sessions = bridge.get("sessions", {})
    if sessions and not isinstance(sessions, dict):
        errors.append("bridge.sessions: must be a mapping")
    elif isinstance(sessions, dict):
        for f in ("workspace_root", "runtime_snapshots_root", "sandbox_backend"):
            if f in sessions and sessions[f] is not None and not isinstance(sessions[f], str):
                errors.append(f"bridge.sessions.{f}: must be a string")
    agent = bridge.get("agent", {})
    if agent and not isinstance(agent, dict):
        errors.append("bridge.agent: must be a mapping")
    elif isinstance(agent, dict):
        for f in ("backend", "permission_handling"):
            if f in agent and agent[f] is not None and not isinstance(agent[f], str):
                errors.append(f"bridge.agent.{f}: must be a string")
    if enabled is True:
        auth = bridge.get("auth", {})
        if not isinstance(auth, dict):
            auth = {}
        for key in ("allowed_users", "admin_users"):
            val = auth.get(key)
            if not isinstance(val, list) or len(val) == 0 or not all(
                isinstance(x, str) and x for x in val
            ):
                errors.append(
                    f"bridge.auth.{key}: required non-empty list of strings when bridge.enabled is true"
                )


def _errs_advanced(adv: Any, errors: list[str]) -> None:
    if adv is None:
        return
    if not isinstance(adv, dict):
        errors.append("advanced: must be a mapping")
        return
    for f in ("model", "output_style"):
        if f in adv and adv[f] is not None and not isinstance(adv[f], str):
            errors.append(f"advanced.{f}: must be a string or null")
    if "worktree" in adv and adv["worktree"] is not None and not isinstance(adv["worktree"], dict):
        errors.append("advanced.worktree: must be a mapping")


def validate_config(
    config: Any, errors: list[str], is_layer: bool = False, prefix: str = ""
) -> None:
    """Validate a parsed instance.yaml (or layer.yaml) mapping, appending
    field-level error strings to `errors`."""
    if not isinstance(config, dict):
        errors.append("instance.yaml: top level must be a mapping")
        return

    if "plugins" in config:
        errors.append(
            "'plugins' is no longer supported. Use skills.yaml instead, "
            "or .claude/settings.local.json for native plugins"
        )

    unknown = set(config.keys()) - TOP_LEVEL_KEYS - {"plugins"}
    for key in sorted(unknown):
        errors.append(f"{key}: unknown top-level key")

    if is_layer:
        forbidden = {"schema_version", "identity", "scope", "base", "layers", "bridge", "escalation"}
        for key in forbidden & set(config.keys()):
            errors.append(f"{key}: not permitted in a layer.yaml (instance-only key)")
    else:
        missing = [k for k in REQUIRED_TOP_LEVEL if k not in config]
        if missing:
            errors.append(f"missing required top-level keys: {missing}")

        sv = config.get("schema_version")
        if "schema_version" in config and sv != 1:
            errors.append(f"schema_version: must be int literal 1, got {sv!r}")

        identity = config.get("identity")
        if "identity" in config:
            if not isinstance(identity, dict):
                errors.append("identity: must be a mapping")
            else:
                if not _is_nonempty_str(identity.get("id")):
                    errors.append("identity.id: must be a non-empty string")
                if not _is_nonempty_str(identity.get("team")):
                    errors.append("identity.team: must be a non-empty string")
                if "description" in identity and not isinstance(identity["description"], str):
                    errors.append("identity.description: must be a string")

        scope = config.get("scope")
        if "scope" in config:
            if not isinstance(scope, dict):
                errors.append("scope: must be a mapping")
            else:
                catalog = scope.get("service_catalog")
                if (
                    not isinstance(catalog, list)
                    or len(catalog) == 0
                    or not all(isinstance(x, str) and x.strip() for x in catalog)
                ):
                    errors.append(
                        "scope.service_catalog: must be a non-empty list of non-empty strings"
                    )

        base = config.get("base")
        if "base" in config:
            if not isinstance(base, dict):
                errors.append("base: must be a mapping")
            else:
                if not _is_nonempty_str(base.get("version")):
                    errors.append("base.version: must be a non-empty string")
                if "branch" in base and base["branch"] is not None and not isinstance(base["branch"], str):
                    errors.append("base.branch: must be a string")
                if "repo" in base and base["repo"] is not None and not isinstance(base["repo"], str):
                    errors.append("base.repo: must be a string")

        layers = config.get("layers")
        if layers is not None:
            if not isinstance(layers, list):
                errors.append("layers: must be a list")
            else:
                names = set()
                for i, layer in enumerate(layers):
                    if not isinstance(layer, dict):
                        errors.append(f"layers[{i}]: must be a mapping")
                        continue
                    name = layer.get("name")
                    if not _is_nonempty_str(name):
                        errors.append(f"layers[{i}].name: must be a non-empty string")
                    elif name in names:
                        errors.append(f"layers[{i}].name: duplicate name '{name}'")
                    else:
                        names.add(name)
                    if not _is_nonempty_str(layer.get("repo")):
                        errors.append(f"layers[{i}].repo: must be a non-empty string")
                    if "version" in layer and not isinstance(layer["version"], str):
                        errors.append(f"layers[{i}].version: must be a string")

        claude_md = config.get("claude_md")
        if claude_md is not None:
            if not isinstance(claude_md, dict):
                errors.append("claude_md: must be a mapping")
            elif "extra_rules" in claude_md and not isinstance(claude_md["extra_rules"], str):
                errors.append("claude_md.extra_rules: must be a string")

        _errs_bridge(config.get("bridge"), errors)
        _errs_advanced(config.get("advanced"), errors)
        _errs_escalation(config.get("escalation"), errors)

    # Sections shared between instance.yaml and layer.yaml
    _errs_settings(config.get("settings"), errors)
    _errs_mcp(config.get("mcp"), errors)
    _errs_kb(config.get("kb"), errors)


def load_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_and_validate(instance_dir: Path) -> dict:
    """Load instance.yaml + VERSION, validate, return the parsed config dict.
    Raises ValidationError with a bulleted, field-level message on any failure.
    """
    errors: list[str] = []

    instance_yaml_path = instance_dir / "instance.yaml"
    if not instance_yaml_path.is_file():
        raise ValidationError(f"instance.yaml not found at {instance_yaml_path}")

    try:
        config = load_yaml(instance_yaml_path)
    except yaml.YAMLError as e:
        raise ValidationError(f"instance.yaml: YAML parse error: {e}") from e

    validate_config(config, errors, is_layer=False)

    version_path = instance_dir / "VERSION"
    if not version_path.is_file():
        errors.append("VERSION: file not found")
    else:
        version_text = version_path.read_text(encoding="utf-8").strip()
        if not SEMVER_RE.match(version_text):
            errors.append(f"VERSION: '{version_text}' is not valid semver X.Y.Z")

    if errors:
        bullet_list = "\n".join(f"  - {e}" for e in errors)
        raise ValidationError(f"instance configuration has {len(errors)} error(s):\n{bullet_list}")

    return config


def main(instance_dir: Path, extra: list[str]) -> int:
    load_and_validate(instance_dir)
    print("instance configuration is valid.")
    return 0


if __name__ == "__main__":
    from builder.cli_common import run_entrypoint

    run_entrypoint(main)
