"""Actor/session/view-bound controls; reservations remain inert until completion."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Protocol

from ..config import NavigationConfig
from ..engine import native_core
from ..errors import OperationIdConflict, Overloaded, SessionExpired, StaleView
from ..models import ConversationKey, NavigationToken, VersionedSnapshot
from .state import Conversation, TokenRecord, fingerprint


class TokenOwner(Protocol):
    config: NavigationConfig
    _lock: asyncio.Lock
    _records: dict[ConversationKey, Conversation]

    def _now(self) -> int: ...
    def _prune(self, record: Conversation) -> None: ...
    def _current(self, record: Conversation) -> VersionedSnapshot | None: ...
    def _changed(self, record: Conversation) -> None: ...


def _binding(token: NavigationToken) -> str:
    return fingerprint(
        (
            token.key,
            token.actor_id,
            token.session_id,
            token.view_id,
            token.action,
            token.expires_at,
            token.entry_id,
        )
    )


def _known_tokens(record: Conversation) -> Iterator[TokenRecord]:
    yield from record.tokens.values()
    for operation in record.operations.values():
        yield from operation.token_receipts.values()


class MemoryTokens:
    config: NavigationConfig
    _lock: asyncio.Lock
    _records: dict[ConversationKey, Conversation]

    def _now(self) -> int:
        raise NotImplementedError

    def _prune(self, record: Conversation) -> None:
        raise NotImplementedError

    def _current(self, record: Conversation) -> VersionedSnapshot | None:
        raise NotImplementedError

    def _changed(self, record: Conversation) -> None:
        raise NotImplementedError

    async def reserve_token(
        self, key: ConversationKey, token: NavigationToken, *, operation_id: str
    ) -> NavigationToken:
        from ..json import identifier

        identifier(operation_id, "operation_id")
        if token.key != key or token.actor_id != key.user_id:
            raise StaleView("Token binding differs from conversation")
        digest = _binding(token)
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                raise SessionExpired("Navigation session is absent")
            self._prune(record)
            for previous in _known_tokens(record):
                if previous.operation_id == operation_id:
                    if previous.fingerprint != digest:
                        raise OperationIdConflict("Token reservation ID has different input")
                    return previous.token
            if any(previous.token.token == token.token for previous in _known_tokens(record)):
                raise OperationIdConflict("Opaque token is reserved by another operation")
            current = self._current(record)
            pending = record.operations.get(record.pending_id) if record.pending_id else None
            prepared = pending.prepared if pending else None
            active = current.snapshot if current else None
            expected_expiry = None
            if (
                prepared is not None
                and prepared.session_id == token.session_id
                and prepared.view_id == token.view_id
            ):
                expected_expiry = prepared.expires_at
            elif (
                active is not None
                and active.session_id == token.session_id
                and active.view.view_id == token.view_id
            ):
                expected_expiry = active.expires_at
            if (
                expected_expiry is None
                or token.expires_at > expected_expiry
                or token.expires_at <= self._now()
            ):
                raise StaleView("Token has no current or prepared navigation view")
            if len(record.tokens) >= self.config.max_tokens:
                raise Overloaded("Navigation token capacity exhausted")
            owner = next(
                (
                    entry
                    for entry in record.operations.values()
                    if entry.prepared is not None
                    and entry.prepared.session_id == token.session_id
                    and entry.prepared.view_id == token.view_id
                ),
                None,
            )
            if owner is not None and len(owner.token_receipts) >= self.config.max_tokens:
                raise Overloaded("Prepared-view control receipt capacity exhausted")
            entry = TokenRecord(token, operation_id, digest)
            record.tokens[token.token] = entry
            if owner is not None:
                owner.token_receipts[operation_id] = entry
            self._changed(record)
            return token

    def _token(self, key: ConversationKey, token: str, record: Conversation) -> TokenRecord | None:
        entry = record.tokens.get(token)
        current = self._current(record)
        if entry is None or current is None:
            return None
        bound, snapshot = entry.token, current.snapshot
        if self.config.engine == "rust":
            valid = native_core().token_matches(
                repr(bound.key),
                repr(key),
                str(bound.actor_id),
                str(key.user_id),
                bound.session_id,
                snapshot.session_id,
                bound.view_id,
                snapshot.view.view_id,
                str(bound.expires_at),
                str(self._now()),
            )
            return entry if valid else None
        if (
            bound.key != key
            or bound.expires_at <= self._now()
            or bound.session_id != snapshot.session_id
            or bound.view_id != snapshot.view.view_id
        ):
            return None
        return entry

    async def resolve_token(self, key: ConversationKey, token: str) -> NavigationToken | None:
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                return None
            entry = self._token(key, token, record)
            return entry.token if entry is not None else None

    async def consume_token(
        self, key: ConversationKey, token: str, *, actor_id: int, operation_id: str
    ) -> NavigationToken:
        from ..json import identifier

        identifier(operation_id, "operation_id")
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                raise StaleView("Navigation control is stale")
            if type(actor_id) is not int or actor_id != key.user_id:
                raise StaleView("Navigation control belongs to another actor")
            for previous in _known_tokens(record):
                if previous.consumed_by == operation_id:
                    if previous.token.token != token:
                        raise OperationIdConflict("Control action ID belongs to another token")
                    return previous.token
            entry = self._token(key, token, record)
            if entry is None or actor_id != entry.token.actor_id:
                raise StaleView("Navigation control is stale or belongs to another actor")
            if entry.consumed_by not in {None, operation_id}:
                raise StaleView("Navigation control was consumed by another operation")
            if entry.consumed_by is None:
                entry.consumed_by = operation_id
                self._changed(record)
            return entry.token
