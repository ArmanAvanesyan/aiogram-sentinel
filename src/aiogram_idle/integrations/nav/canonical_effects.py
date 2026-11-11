"""Navigation UI stages live in their one canonical operation, not Idle acknowledgements."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Literal, TypeVar, cast

from aiogram_nav.codec import decode, encode
from aiogram_nav.models import EffectCheckpoint, PreparedAction, RenderResult

from ...effect_scope import scope_for, stack
from ...effects import OperationEffects, internal_id
from ...errors import EffectUnknown, OwnershipLost
from ...models import RuntimeSnapshot

if TYPE_CHECKING:
    from aiogram_nav.models import ConversationKey

    from .repository import NavigationRepository

T = TypeVar("T")


class CanonicalNavigationEffects:
    def __init__(
        self,
        outer: OperationEffects,
        repo: NavigationRepository,
        key: ConversationKey,
        operation_id: str,
    ):
        self.outer, self.repo, self.key, self.operation_id = outer, repo, key, operation_id
        self._scope = repo.coordinator.scope_token(key)
        self._effect_scope = scope_for(
            outer.runtime.coordinator,
            outer.runtime.coordinator.scope_token(outer.key),
            outer.key,
            internal_id(outer.operation_id, "canonical:" + operation_id),
        )

    async def _prepared(self):
        if self._scope is None or not self.repo.coordinator.scope_matches(self.key, self._scope):
            raise OwnershipLost("Canonical navigation stage ownership ended")
        status = await self.repo.lookup_operation(self.key, operation_id=self.operation_id)
        if status.prepared is None or status.status not in {"prepared", "unknown"}:
            raise OwnershipLost("Canonical navigation operation is no longer pending")
        return status.prepared

    async def record(self) -> RuntimeSnapshot:
        record = await self.outer.record()
        assert record.idle.operation is not None
        prepared = await self._prepared()
        return replace(
            record,
            idle=replace(
                record.idle,
                operation=replace(
                    record.idle.operation,
                    effects={
                        **record.idle.operation.effects,
                        **{stage: effect.state for stage, effect in prepared.effects.items()},
                    },
                ),
            ),
        )

    async def checkpoint(self, stage: str, state: str) -> None:
        if state not in {"started", "confirmed", "not_sent", "unknown"}:
            raise ValueError("Unknown canonical effect stage")
        await self.outer.record()
        await self.repo.checkpoint(
            self.key,
            operation_id=self.operation_id,
            effect=EffectCheckpoint(
                stage, cast(Literal["started", "confirmed", "not_sent", "unknown"], state)
            ),
            coordination_scope=self._scope,
        )

    async def _authorize(self, prepared: PreparedAction) -> None:
        record = await self.outer.record()
        await self.repo.idle.authorize(record)
        nav = self.repo.navigation
        if nav is None:
            raise OwnershipLost("Canonical renderer has no navigation owner")
        await nav.authorize_session(self.key, prepared.session_id)
        node = nav.registry.get(prepared.intent.node_id)
        params = nav.registry.validate_params(node.id, prepared.intent.params)
        await nav.allowed(self.key, node, params, "idle")
        # Access hooks are arbitrary application code. Recheck both authorities
        # and operation ownership after they return, before invoking the effect.
        await nav.authorize_session(self.key, prepared.session_id)
        await self.repo.idle.authorize(await self.outer.record())
        await self._prepared()
        if self.outer.claim is not None:
            await self.outer.runtime.backend.validate_claim(self.outer.claim)

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

    async def _run(
        self, stage: str, effect: Callable[[], Awaitable[T]], *, replay_safe: bool = False
    ) -> T:
        record = await self.outer.record()
        await self.repo.idle.authorize(record)
        prepared = await self._prepared()
        existing = prepared.effects.get(stage)
        if existing is not None and existing.state == "confirmed":
            if isinstance(existing.result, RenderResult):
                return cast(T, existing.result)
            if not isinstance(existing.result, str):
                raise EffectUnknown("Canonical stage receipt is malformed")
            return cast(T, decode(existing.result))
        if existing is not None and existing.state in {"started", "unknown"} and not replay_safe:
            raise EffectUnknown("Canonical UI delivery is uncertain; automatic resend suppressed")
        await self._authorize(prepared)
        if existing is None or existing.state == "not_sent":
            await self.repo.checkpoint(
                self.key,
                operation_id=self.operation_id,
                effect=EffectCheckpoint(stage, "started"),
                coordination_scope=self._scope,
            )
        try:
            await self._authorize(await self._prepared())
        except Exception:
            if existing is None or existing.state == "not_sent":
                await self.checkpoint(stage, "not_sent")
            raise
        # No fallback occurs after reserving this intent. Cancellation retains it.
        result = await effect()
        await self.outer.record()
        evidence = result if isinstance(result, RenderResult) else encode(result)
        await self.repo.checkpoint(
            self.key,
            operation_id=self.operation_id,
            effect=EffectCheckpoint(stage, "confirmed", evidence),
            coordination_scope=self._scope,
        )
        return result
