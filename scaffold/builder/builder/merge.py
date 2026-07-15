"""Merge semantics — the invariants that make multi-tenancy safe.

Pure functions: inputs in, new values out (or a typed error raised).
Spec: docs/10-scaffold/design.md §4.
"""

from __future__ import annotations

from builder.errors import BuildConflictError, MonotonicityError

# Strictness order, most -> least restrictive. No other modes exist.
PERMISSION_STRICTNESS = ("plan", "default", "acceptEdits", "bypassPermissions")

# The mode the base template renders when no override is supplied
# (settings.json.j2: `default_mode | default('acceptEdits', true)`).
BASE_DEFAULT_MODE = "acceptEdits"

# Keys the base template sets in `env` (settings.json.j2).
BASE_ENV_KEYS = frozenset({"CHANGE_GATEWAY_BASE"})

# MCP server names that can never be disabled or overridden by an instance.
PROTECTED_MCP_SERVERS = frozenset({"de-agent-escalate"})


def check_monotonic_mode(requested_mode: str | None, base_mode: str = BASE_DEFAULT_MODE) -> str:
    """Return the effective default_mode, raising MonotonicityError if the
    instance requested something less restrictive than base."""
    if requested_mode is None:
        return base_mode
    if requested_mode not in PERMISSION_STRICTNESS:
        raise MonotonicityError(
            f"settings.permissions.default_mode: '{requested_mode}' is not a valid "
            f"permission mode ({list(PERMISSION_STRICTNESS)})"
        )
    base_idx = PERMISSION_STRICTNESS.index(base_mode)
    req_idx = PERMISSION_STRICTNESS.index(requested_mode)
    if req_idx > base_idx:
        raise MonotonicityError(
            f"settings.permissions.default_mode: '{requested_mode}' is less restrictive than "
            f"base mode '{base_mode}' (strictness order: {' > '.join(PERMISSION_STRICTNESS)}). "
            "Instances may only move toward stricter modes."
        )
    return requested_mode


def check_env_immutable(overlay_env: dict, base_keys: frozenset[str] = BASE_ENV_KEYS) -> dict:
    """Return the overlay env dict if it does not attempt to override any
    base-owned key; otherwise raise BuildConflictError."""
    overlay_env = overlay_env or {}
    collisions = sorted(set(overlay_env.keys()) & base_keys)
    if collisions:
        raise BuildConflictError(
            f"settings.env: instance may not override immutable base env key(s): {collisions}"
        )
    return overlay_env


def merge_disable_servers(
    disable_servers: list[str], protected: frozenset[str] = PROTECTED_MCP_SERVERS
) -> list[str]:
    """Filter out protected server names — they can never be disabled by an
    instance, regardless of what the instance asks for."""
    return [name for name in (disable_servers or []) if name not in protected]


def merge_directory_map(base_map: dict[str, str], overlay_map: dict[str, str], overlay_source: str) -> dict[str, str]:
    """base_map / overlay_map: relative-path -> source label. Any path present
    in both raises BuildConflictError (no-shadowing, ever)."""
    collisions = sorted(set(base_map.keys()) & set(overlay_map.keys()))
    if collisions:
        bullet_list = "\n".join(f"  - {p}" for p in collisions)
        raise BuildConflictError(
            f"{overlay_source} file(s) shadow base-owned runtime path(s):\n{bullet_list}"
        )
    merged = dict(base_map)
    merged.update(overlay_map)
    return merged
