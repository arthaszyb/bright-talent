"""Inbound-text sanitization (platform-governance.md §7 item 4).

Chat text arrives from an untrusted surface. Before the bridge injects it
into an agent session — where authentic framing like the memory context
block exists — we neutralize markup that could impersonate that framing:

- angle-bracket tags that mimic harness/identity envelopes
  (<system>, <untrusted_data>, <function_results>, ...)
- line-leading [role] markers that mimic the memory recall format
- ASCII control characters (except newline/tab)

Neutralize, don't reject: the text stays readable, the markup loses its
teeth. Every strip is logged with a count so tampering attempts are
visible in bridge logs.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("bridge.sanitize")

# Tag names that could impersonate harness, identity, or bridge framing.
_ENVELOPE_TAGS = (
    "untrusted_data",
    "system",
    "assistant",
    "user",
    "human",
    "function_results",
    "function_calls",
    "antml",
    "context",
    "memory",
    "de_context",
    "de_identity",
)

_TAG_RE = re.compile(
    r"</?\s*(?:" + "|".join(_ENVELOPE_TAGS) + r")\b[^>]*>",
    re.IGNORECASE,
)

# Line-leading role markers imitating the memory block's "[role] content".
_ROLE_LINE_RE = re.compile(r"(?m)^(\s*)\[(system|assistant|user)\]", re.IGNORECASE)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_inbound_text(text: str) -> str:
    """Neutralize framing-impersonation markup in inbound chat text."""
    if not text:
        return text

    stripped_controls = _CONTROL_RE.subn("", text)
    tags_removed = _TAG_RE.subn("", stripped_controls[0])
    roles_softened = _ROLE_LINE_RE.subn(r"\1(\2)", tags_removed[0])

    total = stripped_controls[1] + tags_removed[1] + roles_softened[1]
    if total:
        logger.warning(
            "sanitize: neutralized %d suspicious construct(s) in inbound text "
            "(%d control chars, %d envelope tags, %d role markers)",
            total, stripped_controls[1], tags_removed[1], roles_softened[1],
        )
    return roles_softened[0]
