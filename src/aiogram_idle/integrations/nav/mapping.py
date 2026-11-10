"""Lossless identity, clock and coordination mapping at the optional boundary."""

from __future__ import annotations

from collections.abc import Hashable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import cast

from aiogram_nav.models import ConversationKey

from ...clock import Clock
from ...errors import ConfigurationError
from ...models import IdleConversationKey
from ...protocols import Coordinator


@dataclass(frozen=True)
class IdentityMapping:
    """Preserve every supported identity field; no prefix-based aliasing."""

    def to_idle(self, key: ConversationKey) -> IdleConversationKey:
        if not isinstance(cast(object, key), ConversationKey):
            raise ConfigurationError("Expected a navigation conversation identity")
        return IdleConversationKey(
            key.namespace, key.bot_id, key.chat_id, key.user_id, key.tenant_id
        )

    def to_nav(self, key: IdleConversationKey) -> ConversationKey:
        return ConversationKey(key.namespace, key.bot_id, key.chat_id, key.user_id, key.tenant_id)


class VerifiedIdentityMapping(IdentityMapping):
    """Check custom mappings at every boundary before accessing owned storage."""

    def __init__(self, source: IdentityMapping) -> None:
        self.source = source

    def to_idle(self, key: ConversationKey) -> IdleConversationKey:
        expected = super().to_idle(key)
        result = self.source.to_idle(key)
        if type(result) is not IdleConversationKey or result != expected:
            raise ConfigurationError("Identity mapping must preserve every conversation field")
        returned = self.source.to_nav(result)
        if type(returned) is not ConversationKey or returned != key:
            raise ConfigurationError("Identity mapping must round-trip losslessly")
        return result

    def to_nav(self, key: IdleConversationKey) -> ConversationKey:
        expected = super().to_nav(key)
        result = self.source.to_nav(key)
        if type(result) is not ConversationKey or result != expected:
            raise ConfigurationError("Identity mapping must preserve every conversation field")
        returned = self.source.to_idle(result)
        if type(returned) is not IdleConversationKey or returned != key:
            raise ConfigurationError("Identity mapping must round-trip losslessly")
        return result


class NavigationClock:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def now(self) -> int:
        return int(self.clock.now() * 1000)

    def now_ms(self) -> int:
        return self.now()

    def monotonic(self) -> float:
        return self.clock.monotonic()

    async def sleep(self, seconds: float) -> None:
        await self.clock.sleep(seconds)


class MappedCoordinator:
    """One underlying lock domain, with separate public identity types."""

    def __init__(self, coordinator: Coordinator, mapping: IdentityMapping) -> None:
        self.underlying = coordinator
        self.source = coordinator
        self.mapping = mapping

    @property
    def distributed(self) -> bool:
        return getattr(self.underlying, "distributed", False) is True

    @property
    def active_scopes(self) -> int:
        return self.underlying.active_scopes

    def _key(self, key: Hashable) -> IdleConversationKey:
        return self.mapping.to_idle(cast(ConversationKey, key))

    def hold(self, key: Hashable) -> AbstractAsyncContextManager[None]:
        return self.underlying.hold(self._key(key))

    def scope_token(self, key: Hashable) -> object | None:
        return self.underlying.scope_token(self._key(key))

    def scope_active(self, token: object) -> bool:
        return self.underlying.scope_active(token)

    def scope_matches(self, key: Hashable, token: object) -> bool:
        return self.underlying.scope_matches(self._key(key), token)
