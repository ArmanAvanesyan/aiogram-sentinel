"""
Policies & flags:
- CommandPolicy: returns a list of command names from user Flags.
- ProfileResolver: returns a profile name (for config-driven mode).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Flags:
    """User flags that determine which commands are available."""

    is_registered: bool
    has_vehicle: bool
    is_during_registration: bool = False


class CommandPolicy(Protocol):
    """Protocol for command policy functions."""

    def __call__(self, flags: Flags) -> list[str]: ...


class ProfileResolver(Protocol):
    """Resolve a profile name for a given user Flags (for CmdsConfig mode)."""

    def __call__(self, flags: Flags) -> str: ...


def default_policy(flags: Flags) -> list[str]:
    """
    Minimal, project-agnostic command policy.
    """
    if flags.is_during_registration or not flags.is_registered:
        return ["start", "cancel"]
    return ["start", "help", "cancel", "profile", "settings"]
