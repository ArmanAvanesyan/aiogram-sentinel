"""Stage-level intent and receipt checkpoints for external effects."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from hashlib import sha256
from typing import TYPE_CHECKING, TypeVar, cast

from aiogram.exceptions import TelegramRetryAfter

from .effect_scope import scope_for, stack
from .errors import EffectUnknown, OwnershipLost
from .models import ActionReceipt, Phase
from .receipts import decode_result, encode_result

if TYPE_CHECKING:
    from .models import IdleConversationKey, RuntimeSnapshot
    from .runtime import IdleRuntime
    from .storage.state import Claim

T = TypeVar("T")


def internal_id(operation_id: str, stage: str) -> str:
    """Bound derived IDs independently of the caller's valid ID length."""
    return sha256(f"{len(operation_id)}:{operation_id}:{stage}".encode()).hexdigest()


class OperationEffects:
    def __init__(
        self,
        runtime: IdleRuntime,
        key: IdleConversationKey,
        operation_id: str,
        claim: Claim | None,
    ) -> None:
        self.runtime = runtime
        self.key = key
        self.operation_id = operation_id
        self.claim = claim
        self._scope = runtime.coordinator.scope_token(key)
        self._generation: tuple[str, str] | None = None
        self.before_effect: Callable[[RuntimeSnapshot, str], None] | None = None
        self._effect_scope = scope_for(runtime.coordinator, self._scope, key, operation_id)

    async def record(self) -> RuntimeSnapshot:
        if self.runtime.component_validator is not None:
            self.runtime.component_validator()
        if self._scope is None or not self.runtime.coordinator.scope_matches(self.key, self._scope):
            raise OwnershipLost("Effect recorder scope has ended")
        record = await self.runtime.backend.load(self.key)
        if self.runtime.component_validator is not None:
            self.runtime.component_validator()
        if (
            record is None
            or not self.runtime.coordinator.scope_matches(self.key, self._scope)
            or record.idle.operation is None
            or record.idle.operation.operation_id != self.operation_id
            or record.activity is None
            or record.idle.phase
            not in {Phase.PROMPT_PENDING, Phase.RESUMING, Phase.ABANDONING, Phase.RESTORING}
        ):
            raise OwnershipLost("Operation was replaced")
        # Ownership/state checks above enforce this invariant.
        assert record.activity is not None  # nosec B101
        generation = (record.session.session_id, record.activity.activity_id)
        if self._generation is None:
            self._generation = generation
        elif self._generation != generation:
            raise OwnershipLost("Effect recorder activity generation changed")
        return record

    async def checkpoint(self, stage: str, state: str, result: object = None) -> None:
        async with self._effect_scope.checkpoint:
            await self._checkpoint(stage, state, result)

    async def _checkpoint(self, stage: str, state: str, result: object = None) -> None:
        record = await self.record()
        operation = record.idle.operation
        # State already checked by record().
        assert operation is not None  # nosec B101
        effects = dict(operation.effects)
        effects[stage] = state
        if state == "confirmed":
            effects[f"result:{stage}"] = encode_result(result)
        changed = replace(operation, stage=stage, effects=effects)
        await self.runtime.backend.transition(
            self.key,
            expected_version=record.store_version,
            operation_id=internal_id(
                self.operation_id, f"stage:{stage}:{state}:{operation.attempts}"
            ),
            fingerprint=f"{self.operation_id}:{stage}:{state}",
            claim=self.claim,
            coordination_scope=self._scope,
            transform=lambda old: replace(old, idle=replace(old.idle, operation=changed)),
        )

    async def run(
        self, stage: str, effect: Callable[[], Awaitable[T]], *, replay_safe: bool = False
    ) -> T:
        if not stage or len(stage) > 128 or stage.startswith("result:"):
            raise ValueError("Effect stage name is invalid or reserved")
        scope = self._effect_scope
        if any(
            owner is scope and name == stage and nonce in scope.active
            for owner, name, nonce in stack.get()
        ):
            raise EffectUnknown("Effect stages must not recursively reuse names")
        async with scope.stages.setdefault(stage, asyncio.Lock()):
            nonce = object()
            scope.active.add(nonce)
            marker = stack.set((*stack.get(), (scope, stage, nonce)))
            try:
                return await self._run(stage, effect, replay_safe=replay_safe)
            finally:
                scope.active.discard(nonce)
                stack.reset(marker)

    async def _run(self, stage: str, effect: Callable[[], Awaitable[T]], *, replay_safe: bool) -> T:
        record = await self.record()
        operation = record.idle.operation
        # State already checked by record().
        assert operation is not None  # nosec B101
        # State already checked by record().
        assert record.activity is not None  # nosec B101
        state = operation.effects.get(stage)
        if state == "started" and not replay_safe:
            raise EffectUnknown("Unconfirmed effect cannot be replayed")
        if state == "confirmed":
            return cast(T, decode_result(operation.effects.get(f"result:{stage}")))
        if min(record.session.expires_at, record.activity.expires_at) <= self.runtime.clock.now():
            raise OwnershipLost("Logical activity expired before an external stage")
        if state != "started":
            await self.checkpoint(stage, "started")
        record = await self.record()
        # State already checked by record().
        assert record.activity is not None  # nosec B101
        if min(record.session.expires_at, record.activity.expires_at) <= self.runtime.clock.now():
            raise OwnershipLost("Logical activity expired before an external stage")
        if self.claim is not None:
            await self.runtime.backend.validate_claim(self.claim)
        if self.before_effect is not None:
            try:
                self.before_effect(record, stage)
            except Exception:
                # This stage has durably reserved intent but has made no request.
                await self.checkpoint(stage, "not_sent")
                raise
        try:
            result = await effect()
        except TelegramRetryAfter:
            await self.checkpoint(stage, "not_sent")
            raise
        if isinstance(result, ActionReceipt) and result.operation_id not in {"", self.operation_id}:
            raise EffectUnknown("Adapter receipt belongs to another operation")
        await self.checkpoint(stage, "confirmed", result)
        return result
