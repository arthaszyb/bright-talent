"""Built-in slash commands for the bridge demo."""
from __future__ import annotations

from .sessions import SessionManager

VALID_PERMISSION_MODES = {"plan", "default", "acceptEdits", "bypassPermissions"}

# Strictness order, most -> least restrictive (mirrors the builder's
# PERMISSION_STRICTNESS). A chat user may only tighten toward the left of the
# base mode; loosening to the right is a privilege escalation and needs admin.
PERMISSION_STRICTNESS = ("plan", "default", "acceptEdits", "bypassPermissions")

PERMISSION_ESCALATION_MESSAGE = (
    "Loosening the permission mode beyond the instance default requires admin "
    "privileges — non-admins may only select an equal or stricter mode."
)


def loosens_beyond(requested: str, base: str) -> bool:
    """True if `requested` is a valid mode strictly less restrictive than `base`."""
    if requested not in PERMISSION_STRICTNESS or base not in PERMISSION_STRICTNESS:
        return False
    return PERMISSION_STRICTNESS.index(requested) > PERMISSION_STRICTNESS.index(base)

HELP_TEXT = (
    "/help - show this help\n"
    "/reset - forget this thread's session and start fresh\n"
    "/cd <dir> - change this session's working directory (admin only)\n"
    "/pwd - show this session's current working directory\n"
    "/plan - switch permission mode to plan for the next session start\n"
    "/mode <m> - set permission mode (plan/default/acceptEdits/bypassPermissions) for the next session start"
)

ADMIN_COMMANDS = ("/cd",)


def is_command(text: str) -> bool:
    text = text.strip()
    return text.split(" ", 1)[0] in (
        "/help",
        "/reset",
        "/cd",
        "/pwd",
        "/plan",
        "/mode",
    ) if text else False


async def handle_command(
    text: str,
    key: str,
    sessions: SessionManager,
    *,
    is_admin: bool = False,
    base_mode: str = "acceptEdits",
) -> str:
    text = text.strip()
    parts = text.split(" ", 1)
    token = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    if token == "/help":
        return HELP_TEXT

    if token == "/reset":
        await sessions.reset_async(key)
        return "Session reset."

    if token == "/cd":
        if not rest:
            return "Usage: /cd <dir>"
        sessions.set_cwd_override(key, rest)
        return f"Working directory set to {rest} (applies on next session start)."

    if token == "/pwd":
        return sessions.get_working_dir(key)

    if token == "/plan":
        sessions.set_permission_mode_override(key, "plan")
        return "Permission mode set to plan (applies on next session start)."

    if token == "/mode":
        if rest not in VALID_PERMISSION_MODES:
            return f"Usage: /mode <{'|'.join(sorted(VALID_PERMISSION_MODES))}>"
        if not is_admin and loosens_beyond(rest, base_mode):
            return PERMISSION_ESCALATION_MESSAGE
        sessions.set_permission_mode_override(key, rest)
        return f"Permission mode set to {rest} (applies on next session start)."

    return f"Unknown command: {token}"
