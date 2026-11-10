"""A backend has exactly one coordinator across all attached runtimes."""

from __future__ import annotations

from ..errors import ConfigurationError
from ..protocols import Coordinator


def bind(current: Coordinator, proposed: Coordinator, *, has_records: bool) -> Coordinator:
    if proposed is current:
        return current
    if has_records or current.active_scopes:
        raise ConfigurationError("Cannot replace a coordinator after activity has started")
    return proposed


def check_manifest(actual: str | None, expected: str | None) -> None:
    from ..errors import ConfigurationMismatch

    if expected is not None and actual != expected:
        raise ConfigurationMismatch("Configuration changed before activity commit")
