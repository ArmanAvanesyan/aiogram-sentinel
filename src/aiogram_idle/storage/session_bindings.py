"""Internal projections of application-owned sessions; never application writes."""

from __future__ import annotations

# Backend mixin, with the same private storage protocol as component transactions.
# pyright: reportPrivateUsage=false
import asyncio
import secrets
from collections.abc import Mapping
from typing import Protocol, cast

from ..errors import ActivityConflict, ConfigurationError, SessionExpired
from ..models import IdleConversationKey, RuntimeSnapshot, SessionSnapshot
from .receipts import Receipts, fingerprint
from .retention import ensure_activity_mutable

EXTERNAL_SESSION = "__external_session__"


class BindingOwner(Protocol):
    _lock: asyncio.Lock
    _records: dict[IdleConversationKey, RuntimeSnapshot]
    _receipts: Receipts

    def _now(self) -> float: ...
    def _capacity(self) -> None: ...
    def _save(self, record: RuntimeSnapshot) -> RuntimeSnapshot: ...
    async def require_storage_format(self, version: int) -> None: ...


class SessionBindings:
    async def bind_external_session(
        self: BindingOwner,
        key: IdleConversationKey,
        *,
        session_id: str,
        revision: str,
        absolute_expires_at: int,
        operation_id: str,
    ) -> SessionSnapshot:
        await self.require_storage_format(2)
        if (
            not session_id
            or not isinstance(cast(object, session_id), str)
            or not revision
            or not isinstance(cast(object, revision), str)
            or type(absolute_expires_at) is not int
        ):
            raise ConfigurationError("Invalid application session binding")
        async with self._lock:
            now = self._now()
            digest = fingerprint(("external-session", session_id, absolute_expires_at))
            duplicate = self._receipts.prepare(key, operation_id, digest, now=now)
            if duplicate is not None:
                return cast(SessionSnapshot, duplicate)
            if absolute_expires_at <= now * 1000:
                raise SessionExpired("Application session expired")
            existing = self._records.get(key)
            binding = existing.components.get(EXTERNAL_SESSION) if existing else None
            if (
                existing is not None
                and isinstance(binding, Mapping)
                and binding.get("session_id") == session_id
            ):
                if binding.get("absolute_expires_at") != absolute_expires_at:
                    raise ActivityConflict("Application absolute session expiry changed")
                return self._receipts.save(key, operation_id, digest, existing.session, now=now)
            if existing is not None:
                if existing.idle.operation is not None:
                    raise ActivityConflict(
                        "Unresolved operation evidence prevents session rotation"
                    )
                ensure_activity_mutable(existing)
                if binding is None and existing.session.expires_at > now:
                    raise ActivityConflict("Cannot adopt a live library-owned session")
            else:
                self._capacity()
            session = SessionSnapshot(secrets.token_urlsafe(18), absolute_expires_at / 1000)
            # Receipt history is retained by the backend even when this generation rotates.
            self._save(
                RuntimeSnapshot(
                    key=key,
                    session=session,
                    components={
                        EXTERNAL_SESSION: {
                            "session_id": session_id,
                            "revision": revision,
                            "absolute_expires_at": absolute_expires_at,
                        }
                    },
                )
            )
            return self._receipts.save(key, operation_id, digest, session, now=now)
