"""Atomic adoption of an application-owned render, without invoking external effects."""

from __future__ import annotations

import asyncio
import heapq
from dataclasses import replace

from ..errors import ConfigurationError
from ..models import (
    CommitResult,
    ConversationKey,
    EffectCheckpoint,
    NavigationIntent,
    NavigationMutation,
    PreparedAction,
    RenderResult,
)
from .state import Conversation


class MemoryAdoption:
    _lock: asyncio.Lock
    _records: dict[ConversationKey, Conversation]

    def _prepare_locked(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        raise NotImplementedError

    def _checkpoint_locked(
        self,
        key: ConversationKey,
        *,
        operation_id: str,
        effect: EffectCheckpoint,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        raise NotImplementedError

    def _commit_locked(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        mutation: NavigationMutation,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        raise NotImplementedError

    async def adopt_render(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        rendered: RenderResult,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        if intent.action != "track" or intent.view_id != rendered.view_id:
            raise ConfigurationError("Atomic render adoption requires matching track intent/view")
        async with self._lock:
            record = self._records.get(key)
            original = None
            previous = None
            if record is not None:
                original = record.version, record.current, record.pending_id, dict(record.tokens)
                entry = record.operations.get(intent.operation_id)
                previous = (
                    replace(entry, token_receipts=dict(entry.token_receipts)) if entry else None
                )
            try:
                prepared = self._prepare_locked(
                    key,
                    expected_version=expected_version,
                    intent=intent,
                    coordination_scope=coordination_scope,
                )
                if prepared.status != "completed":
                    if "render" not in prepared.effects:
                        self._checkpoint_locked(
                            key,
                            operation_id=intent.operation_id,
                            effect=EffectCheckpoint("render", "started"),
                            coordination_scope=coordination_scope,
                        )
                    self._checkpoint_locked(
                        key,
                        operation_id=intent.operation_id,
                        effect=EffectCheckpoint("render", "confirmed", rendered),
                        coordination_scope=coordination_scope,
                    )
                return self._commit_locked(
                    key,
                    expected_version=expected_version,
                    mutation=NavigationMutation(
                        intent.operation_id,
                        prepared.session_id,
                        rendered,
                        accepted_activity=intent.accepted_activity,
                        source=intent.source,
                    ),
                    coordination_scope=coordination_scope,
                )
            except BaseException:
                if record is None:
                    self._records.pop(key, None)
                else:
                    assert original is not None
                    record.version, record.current, record.pending_id, record.tokens = original
                    rejected = record.operations.get(intent.operation_id)
                    if rejected is not None and rejected.prepared is not None:
                        pair = rejected.prepared.session_id, rejected.prepared.view_id
                        if record.views.get(pair) == intent.operation_id:
                            record.views.pop(pair, None)
                    if previous is None:
                        record.operations.pop(intent.operation_id, None)
                    else:
                        record.operations[intent.operation_id] = previous
                        if previous.prepared is not None:
                            record.views[
                                (previous.prepared.session_id, previous.prepared.view_id)
                            ] = intent.operation_id
                        if previous.status in ("completed", "failed"):
                            heapq.heappush(
                                record.expiry_heap, (previous.retention_until, intent.operation_id)
                            )
                    # Expired unrelated evidence may remain reclaimed, but no live
                    # activity, stage or result is partially adopted on failure.
                    if len(record.expiry_heap) > 2 * len(record.operations) + 128:
                        record.expiry_heap = [
                            (entry.retention_until, operation_id)
                            for operation_id, entry in record.operations.items()
                            if entry.status in ("completed", "failed")
                        ]
                        heapq.heapify(record.expiry_heap)
                raise
