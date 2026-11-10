"""Guarded activity entry points; never infer acceptance from an incoming update."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, cast

from .errors import ConfigurationError, SessionExpired
from .models import (
    ActivityGuard,
    ActivitySnapshot,
    IdleConversationKey,
    SessionGuard,
    SessionSnapshot,
)
from .registration import ActivityRegistration

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .runtime import IdleRuntime


class IdleContext:
    def __init__(self, runtime: IdleRuntime, key: IdleConversationKey) -> None:
        self.runtime = runtime
        self.key = key

    async def open_session(self, *, operation_id: str, lifetime_seconds: float) -> SessionSnapshot:
        if self.runtime.session_authority is not None:
            raise ConfigurationError("Application sessions are owned by SessionAuthority")
        async with self.runtime.coordinator.hold(self.key):
            await self.runtime.initialize()
            return await self.runtime.backend.open_session(
                self.key, lifetime_seconds=lifetime_seconds, operation_id=operation_id
            )

    async def replace_session(
        self, *, expected: SessionGuard, operation_id: str, lifetime_seconds: float
    ) -> SessionSnapshot:
        if self.runtime.session_authority is not None:
            raise ConfigurationError("Application sessions are owned by SessionAuthority")
        async with self.runtime.coordinator.hold(self.key):
            await self.runtime.initialize()
            return await self.runtime.backend.replace_session(
                self.key,
                expected=expected,
                lifetime_seconds=lifetime_seconds,
                operation_id=operation_id,
            )

    async def current(self) -> ActivitySnapshot | None:
        async with self.runtime.coordinator.hold(self.key):
            snapshot = await self.runtime.backend.load(self.key)
            if snapshot is None or snapshot.session.expires_at <= self.runtime.clock.now():
                return None
            try:
                await self.runtime.authorize(snapshot)
            except SessionExpired:
                return None
            if (
                snapshot.activity is not None
                and snapshot.activity.expires_at <= self.runtime.clock.now()
            ):
                return None
            return snapshot.activity

    async def activate(
        self,
        registration: ActivityRegistration,
        *,
        operation_id: str,
        expected: ActivityGuard | None = None,
    ) -> ActivitySnapshot:
        """Enter a registered flow using the current authorized session.

        Owned mode requires an explicitly opened library session. External mode
        projects an existing application session without modifying its authority.
        """
        from .effects import internal_id

        if not isinstance(cast(object, registration), ActivityRegistration):
            raise TypeError("Expected ActivityRegistration")
        async with self.runtime.coordinator.hold(self.key):
            await self.runtime.initialize()
            if self.runtime.session_authority is not None:
                if await self.runtime.backend.storage_format() != 2:
                    raise ConfigurationError("External sessions require activated storage format 2")
                external = await self.runtime.external_session(self.key)
                session = await self.runtime.backend.bind_external_session(
                    self.key,
                    session_id=external.session_id,
                    revision=external.revision,
                    absolute_expires_at=external.absolute_expires_at,
                    operation_id=internal_id(operation_id, "session-binding"),
                )
            else:
                record = await self.runtime.backend.load(self.key)
                if record is None or record.session.expires_at <= self.runtime.clock.now():
                    raise SessionExpired("Open a library session before activating a flow")
                session = record.session
            return await self.enter(
                registration.activity_key,
                policy_id=registration.policy_id,
                adapter_key=registration.adapter_key,
                params=registration.params,
                session_id=session.session_id,
                expires_at=session.expires_at,
                operation_id=operation_id,
                expected=expected,
            )

    async def enter(
        self,
        activity_key: str,
        *,
        policy_id: str,
        adapter_key: str,
        params: Mapping[str, object],
        session_id: str,
        expires_at: datetime | float,
        operation_id: str,
        expected: ActivityGuard | None = None,
    ) -> ActivitySnapshot:
        async with self.runtime.coordinator.hold(self.key):
            await self.runtime.initialize()
            record = await self.runtime.backend.load(self.key)
            if record is not None:
                await self.runtime.authorize(record)
            self.runtime.adapter(adapter_key)
            manifest = await self.runtime.manifest()
            previous = await self.runtime.current_prompt(self.key)
            result = await self.runtime.backend.enter(
                self.key,
                activity_key=activity_key,
                policy_id=policy_id,
                policy=self.runtime.policies[policy_id],
                adapter_key=adapter_key,
                params=params,
                session_id=session_id,
                expires_at=expires_at,
                operation_id=operation_id,
                expected=expected,
                enabled=manifest.enabled,
                expected_manifest=manifest.generation,
            )
            if previous is not None:
                try:
                    await self.runtime.presenter.strip(previous)
                except Exception:
                    logger.warning("Superseded prompt cleanup unavailable")
            return result

    async def touch(self, *, expected: ActivityGuard, operation_id: str) -> ActivitySnapshot:
        async with self.runtime.coordinator.hold(self.key):
            await self.runtime.initialize()
            record = await self.runtime.backend.load(self.key)
            if record is not None:
                await self.runtime.authorize(record)
            manifest = await self.runtime.manifest()
            previous = await self.runtime.current_prompt(self.key)
            result = await self.runtime.backend.touch(
                self.key,
                expected=expected,
                operation_id=operation_id,
                enabled=manifest.enabled,
                expected_manifest=manifest.generation,
            )
            if previous is not None:
                try:
                    await self.runtime.presenter.strip(previous)
                except Exception:
                    logger.warning("Superseded prompt cleanup unavailable")
            return result

    async def clear(self, *, expected: ActivityGuard, reason: str, operation_id: str) -> None:
        async with self.runtime.coordinator.hold(self.key):
            await self.runtime.initialize()
            record = await self.runtime.backend.load(self.key)
            if record is not None:
                await self.runtime.authorize(record)
            await self.runtime.backend.clear(
                self.key, expected=expected, operation_id=operation_id, reason=reason
            )
