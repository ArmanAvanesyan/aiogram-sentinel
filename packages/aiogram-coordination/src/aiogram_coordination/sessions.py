"""Read-only application session authority; persistence remains application-owned."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .errors import ConfigurationError
from .identity import CoordinationKey


@dataclass(frozen=True)
class ExternalSession:
    session_id: str
    revision: str
    absolute_expires_at: int
    idle_expires_at: int | None = None

    def __post_init__(self) -> None:
        for name in ("session_id", "revision"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise ConfigurationError(f"{name} must contain 1 to 256 characters")
        if (
            type(self.absolute_expires_at) is not int
            or not 0 < self.absolute_expires_at <= 253402300799999
        ):
            raise ConfigurationError("Absolute expiry must be bounded UTC epoch milliseconds")
        for value in (self.absolute_expires_at, self.idle_expires_at):
            if value is not None and (type(value) is not int or not 0 < value <= 253402300799999):
                raise ConfigurationError("Session expiry must be positive UTC epoch milliseconds")
        if self.idle_expires_at is not None and self.idle_expires_at > self.absolute_expires_at:
            raise ConfigurationError("Idle expiry cannot exceed absolute expiry")

    @property
    def expires_at(self) -> int:
        return min(self.absolute_expires_at, self.idle_expires_at or self.absolute_expires_at)

    def is_live(self, now_ms: int) -> bool:
        if type(now_ms) is not int or now_ms < 0:
            raise ConfigurationError("Current time must be UTC epoch milliseconds")
        return now_ms < self.expires_at


class SessionAuthority(Protocol):
    async def current(self, key: CoordinationKey) -> ExternalSession | None:
        """None means unauthorized; outages must raise SessionAuthorityUnavailable.

        IDs must never be reused and absolute expiry must not change under one ID.
        Revision is an opaque application revision; it need not be numeric.
        """
        ...


def validate_session_transition(previous: ExternalSession, current: ExternalSession) -> None:
    """Reject a changed immutable absolute expiry under an existing session ID."""
    if (
        previous.session_id == current.session_id
        and previous.absolute_expires_at != current.absolute_expires_at
    ):
        raise ConfigurationError("Absolute expiry cannot change under the same session ID")
