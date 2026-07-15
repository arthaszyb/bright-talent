"""Typed errors raised by the builder and mapped to CLI exit codes by entrypoints.

Per DESIGN.md S1: builder raises typed errors -> non-zero exit with bulleted,
field-level messages on stderr. `de` maps: builder non-zero -> exit 1.
"""


class BuilderError(Exception):
    """Base class for all typed builder errors."""


class ValidationError(BuilderError):
    """instance.yaml (or layer.yaml) failed schema validation."""


class BuildConflictError(BuilderError):
    """A base-owned and instance-owned (or layer-owned) file share the same
    relative runtime path — the no-shadowing invariant. Also raised when an
    instance attempts to override an immutable base env key."""


class MonotonicityError(BuilderError):
    """An instance requested a permission mode less restrictive than base."""


class BuildError(BuilderError):
    """Any other build-time failure not covered by the above."""
