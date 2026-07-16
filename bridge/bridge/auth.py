"""Allowlist / admin gating for the bridge demo."""
from __future__ import annotations

from .config import BridgeConfig

REFUSAL_MESSAGE = "Sorry, that command requires admin privileges."
BASH_NOT_IMPLEMENTED_MESSAGE = "Bash passthrough is not implemented in this demo."


def _candidates(sender: dict) -> set[str]:
    cands = set()
    if not sender:
        return cands
    for key in ("user_id", "email"):
        val = sender.get(key)
        if val:
            cands.add(val)
    return cands


def is_allowed(sender: dict, config: BridgeConfig) -> bool:
    allowed = config.auth.allowed_users
    if not allowed:
        return True
    return bool(_candidates(sender) & set(allowed))


def is_admin(sender: dict, config: BridgeConfig) -> bool:
    admins = config.auth.admin_users
    if not admins:
        return False
    return bool(_candidates(sender) & set(admins))
