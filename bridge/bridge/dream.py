"""Dream consolidation - OUT OF SCOPE for this demo.

The full docs/50-bridge design describes a "dream" service that periodically
consolidates conversation memory into higher-level summaries (managed
workspaces, background consolidation jobs, etc). That machinery is
intentionally not implemented for de-demo: this module exists only so that
config keys and documentation can reference a stable stub surface without
pulling in the full production design.

Not wired into any active loop (no scheduler, no background task starts it).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def check_dream(*args, **kwargs) -> None:
    """No-op stub. Real implementation is out of scope for this demo."""
    logger.info("dream service not implemented in demo")
    return None
