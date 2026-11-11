"""Renewable application Redis FSM isolation with public ownership receipts."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import cast

from aiogram.fsm.storage.base import BaseEventIsolation, DefaultKeyBuilder, KeyBuilder, StorageKey

from .errors import ConfigurationError, OwnershipLost
from .protocols import LeaseHandle
from .redis import RedisCoordinator


@dataclass(frozen=True)
class _FSMKey:
    storage_key: StorageKey

    @property
    def namespace(self) -> str:
        return "fsm"

    @property
    def tenant_id(self) -> None:
        return None

    @property
    def bot_id(self) -> int:
        return self.storage_key.bot_id

    @property
    def chat_id(self) -> int:
        return self.storage_key.chat_id

    @property
    def user_id(self) -> int:
        return self.storage_key.user_id


class _FSMCoordinator(RedisCoordinator):
    def __init__(
        self,
        *,
        redis: object,
        key_builder: KeyBuilder,
        lease_seconds: float,
        renew_seconds: float,
        wait_seconds: float,
        poll_seconds: float,
        io_timeout: float,
    ) -> None:
        self.key_builder = key_builder
        super().__init__(
            redis=redis,
            lease_seconds=lease_seconds,
            renew_seconds=renew_seconds,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            io_timeout=io_timeout,
        )

    def normalize_key(self, key: Hashable) -> Hashable:
        # FSM identity includes thread/destiny/business dimensions beyond a
        # private conversation key; never collapse those to actor identity.
        if not isinstance(key, _FSMKey):
            raise ConfigurationError("Expected a full FSM storage key")
        return key

    def lock_key(self, key: Hashable) -> str:
        if not isinstance(key, _FSMKey):
            raise ConfigurationError("Expected a full FSM storage key")
        try:
            return self.key_builder.build(key.storage_key, "lock")
        except Exception as error:
            raise ConfigurationError("FSM key builder cannot encode this identity") from error


@dataclass
class _RedisLease:
    key: StorageKey
    coordinator: RedisCoordinator
    mapped: _FSMKey
    token: object

    @property
    def valid(self) -> bool:
        return self.coordinator.scope_matches(self.mapped, self.token)

    def assert_owned(self) -> None:
        if not self.valid:
            raise OwnershipLost("Application Redis FSM lease is no longer owned")

    async def wait_lost(self) -> None:
        await self.coordinator.wait_scope_lost(self.token)


class RenewableRedisEventIsolation(BaseEventIsolation):
    """Application-owned FSM lock provider with renewable token-checked leases.

    Reuse the application's Redis client and key builder. This is an explicit
    replacement provider at Dispatcher construction, never an implicit adapter
    over opaque RedisEventIsolation internals. It does not close the client.
    """

    def __init__(
        self,
        *,
        redis: object,
        key_builder: KeyBuilder | None = None,
        lease_seconds: float = 30,
        renew_seconds: float = 10,
        wait_seconds: float = 30,
        poll_seconds: float = 0.05,
        io_timeout: float = 5,
    ) -> None:
        builder = key_builder or DefaultKeyBuilder(
            with_bot_id=True, with_business_connection_id=True, with_destiny=True
        )
        if not isinstance(cast(object, builder), KeyBuilder):
            raise ConfigurationError("FSM isolation requires a public KeyBuilder")
        keys = [
            StorageKey(bot_id=1, chat_id=2, user_id=3),
            StorageKey(bot_id=2, chat_id=2, user_id=3),
            StorageKey(bot_id=1, chat_id=4, user_id=3),
            StorageKey(bot_id=1, chat_id=2, user_id=4),
        ]
        encoded = [builder.build(key, "lock") for key in keys]
        if len(set(encoded)) != len(encoded) or not all(
            isinstance(cast(object, value), str) and value for value in encoded
        ):
            raise ConfigurationError("FSM keys must preserve bot, chat and actor identity")
        base = keys[0]
        dimensions = {
            "thread_id": (11, 12),
            "business_connection_id": ("business-a", "business-b"),
            "destiny": ("other-a", "other-b"),
        }
        supported: set[str] = set()
        for field, variants in dimensions.items():
            try:
                probes = [
                    builder.build(replace(base, **{field: value}), "lock") for value in variants
                ]
                if len(set([encoded[0], *probes])) == 3 and all(
                    isinstance(cast(object, value), str) and value for value in probes
                ):
                    supported.add(field)
            except Exception:
                # A builder can intentionally support private/default FSM only.
                # Such dimensions are rejected before acquiring a Redis lock.
                continue
        self.supported_dimensions = frozenset(supported)
        self._closed = False
        self.key_builder = builder
        self.coordinator = _FSMCoordinator(
            redis=redis,
            key_builder=builder,
            lease_seconds=lease_seconds,
            renew_seconds=renew_seconds,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            io_timeout=io_timeout,
        )

    @property
    def isolation(self) -> BaseEventIsolation:
        return self

    @asynccontextmanager
    async def acquire(self, key: StorageKey) -> AsyncGenerator[LeaseHandle, None]:
        if self._closed or not isinstance(cast(object, key), StorageKey):
            raise ConfigurationError("Expected an FSM StorageKey")
        for field in ("thread_id", "business_connection_id", "destiny"):
            value = getattr(key, field)
            is_default = value is None or (field == "destiny" and value == "default")
            if not is_default and field not in self.supported_dimensions:
                raise ConfigurationError(
                    "FSM key builder cannot preserve requested identity dimensions"
                )
        mapped = _FSMKey(key)
        async with self.coordinator.hold(mapped):
            token = self.coordinator.scope_token(mapped)
            if token is None:
                raise OwnershipLost("No application FSM lease was acquired")
            yield _RedisLease(key, self.coordinator, mapped, token)

    @asynccontextmanager
    async def lock(self, key: StorageKey) -> AsyncGenerator[None, None]:
        async with self.acquire(key) as lease:
            lease.assert_owned()
            yield

    async def close(self) -> None:
        if self.coordinator.active_scopes:
            raise ConfigurationError("Drain application FSM scopes before close")
        self._closed = True
        # Redis lifecycle remains application-owned.


RedisIsolationProvider = RenewableRedisEventIsolation
