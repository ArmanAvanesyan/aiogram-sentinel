"""Lossless full-identity keys shared without importing consuming libraries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from .errors import ConfigurationError


@dataclass(frozen=True)
class CoordinationKey:
    namespace: str
    bot_id: int
    chat_id: int
    user_id: int
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(cast(object, self.namespace), str)
            or not self.namespace
            or len(self.namespace) > 128
        ):
            raise ConfigurationError("Namespace must contain 1 to 128 characters")
        for name in ("bot_id", "chat_id", "user_id"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ConfigurationError(f"{name} must be a positive integer")
        if self.tenant_id is not None and (
            not isinstance(cast(object, self.tenant_id), str)
            or not self.tenant_id
            or len(self.tenant_id) > 128
        ):
            raise ConfigurationError("Tenant must be nonempty text when supplied")


class _Identity(Protocol):
    namespace: str
    bot_id: int
    chat_id: int
    user_id: int
    tenant_id: str | None


def coordination_key(key: object) -> CoordinationKey:
    """Accept validated structural library keys without collapsing any identity."""
    if isinstance(key, CoordinationKey):
        return key
    for field in ("thread_id", "message_thread_id", "business_connection_id", "destiny"):
        value = getattr(key, field, None)
        if value is not None and not (field == "destiny" and value == "default"):
            raise ConfigurationError(
                "Additional FSM identity requires an explicit lossless mapping"
            )
    structural = cast(_Identity, key)
    try:
        return CoordinationKey(
            namespace=structural.namespace,
            bot_id=structural.bot_id,
            chat_id=structural.chat_id,
            user_id=structural.user_id,
            tenant_id=structural.tenant_id,
        )
    except (AttributeError, TypeError) as error:
        raise ConfigurationError("Expected a lossless full conversation identity") from error
