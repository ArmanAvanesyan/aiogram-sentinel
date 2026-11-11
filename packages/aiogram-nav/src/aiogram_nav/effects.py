"""Scoped stage receipts make interrupted renders observable and conservative."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeVar, cast

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from .errors import AccessDenied, InvalidParameters, Overloaded, OwnershipLost, RenderUnknown
from .json import fingerprint
from .models import ConversationKey, EffectCheckpoint, PreparedAction, RenderResult, ViewState
from .protocols import Coordinator

if TYPE_CHECKING:
    from .navigation import Navigation

T = TypeVar("T")
StageKey = tuple[int, int, ConversationKey, str, str]


@dataclass
class _StageEntry:
    coordinator: Coordinator
    scope: object
    lock: asyncio.Lock
    users: int = 0
    execution: object | None = None


# Entries exist only while a stage is running or contended. Sharing by coordinator
# and live scope covers separate recorders/runtimes without granting lock ownership.
_stages: dict[StageKey, _StageEntry] = {}
_running: ContextVar[tuple[tuple[StageKey, object], ...]] = ContextVar(
    "nav_running_stages", default=()
)


@asynccontextmanager
async def _stage_lock(
    coordinator: Coordinator,
    scope: object,
    key: ConversationKey,
    operation_id: str,
    stage: str,
    limit: int,
) -> AsyncGenerator[None, None]:
    identity = (id(coordinator), id(scope), key, operation_id, stage)
    active = _stages.get(identity)
    if active is not None and any(
        held == identity and execution is active.execution for held, execution in _running.get()
    ):
        raise RenderUnknown("An executing stage cannot recursively enter itself")
    if identity not in _stages:
        if sum(item[:4] == identity[:4] for item in _stages) >= limit:
            raise Overloaded("Render effect stage capacity exhausted")
        _stages[identity] = _StageEntry(coordinator, scope, asyncio.Lock())
    entry = _stages[identity]
    entry.users += 1
    try:
        async with entry.lock:
            execution = object()
            entry.execution = execution
            marker = _running.set((*_running.get(), (identity, execution)))
            try:
                yield
            finally:
                entry.execution = None
                _running.reset(marker)
    finally:
        entry.users -= 1
        if entry.users == 0:
            _stages.pop(identity, None)


def normalize_render(result: RenderResult) -> RenderResult:
    """Complete views have the same receipt semantics as RenderResult."""
    if isinstance(result, ViewState) and result.render_status != "complete":
        return result
    return RenderResult(
        result.view_id,
        result.messages,
        result.reply_keyboard_key,
        result.locale,
        result.reply_keyboard_locale,
    )


class NavigationEffects:
    def __init__(self, navigation: Navigation, prepared: PreparedAction) -> None:
        self.navigation = navigation
        self.prepared = prepared
        self.key = prepared.key
        self.operation_id = prepared.operation_id
        self._scope = navigation.coordinator.scope_token(self.key)

    async def record(self, *, allow_expired: bool = False) -> PreparedAction:
        if self._scope is None or not self.navigation.coordinator.scope_matches(
            self.key, self._scope
        ):
            raise OwnershipLost("The render coordination scope has ended")
        status = await self.navigation.repository.lookup_operation(
            self.key, operation_id=self.operation_id
        )
        current = status.prepared
        if (
            current is None
            or current.status not in {"prepared", "unknown"}
            or current.session_id != self.prepared.session_id
            or current.view_id != self.prepared.view_id
            or not self.navigation.coordinator.scope_matches(self.key, self._scope)
            or (not allow_expired and current.expires_at <= self.navigation.clock.now())
        ):
            raise OwnershipLost("The prepared render is no longer current")
        if not allow_expired:
            await self.navigation.authorize_session(self.key, current.session_id)
        return current

    async def checkpoint(self, stage: str, state: str, result: object = None) -> None:
        from .json import freeze_json

        await self.record(allow_expired=state != "started")
        if state not in {"started", "confirmed", "not_sent", "unknown"}:
            raise ValueError("Unsupported effect state")
        receipt = (
            normalize_render(result) if isinstance(result, RenderResult) else freeze_json(result)
        )
        await self.navigation.repository.checkpoint(
            self.key,
            operation_id=self.operation_id,
            effect=EffectCheckpoint(
                stage, cast(Literal["started", "confirmed", "not_sent", "unknown"], state), receipt
            ),
            coordination_scope=self._scope,
        )

    async def run(
        self, stage: str, callback: Callable[[], Awaitable[T]], *, replay_safe: bool = False
    ) -> T:
        if not stage or len(stage) > 128:
            raise RenderUnknown("Effect stages must have distinct bounded names")
        await self.record()
        assert self._scope is not None
        async with _stage_lock(
            self.navigation.coordinator,
            self._scope,
            self.key,
            self.operation_id,
            stage,
            self.navigation.config.max_receipts,
        ):
            current = await self.record()
            previous = current.effects.get(stage)
            if previous is not None and previous.state == "confirmed":
                return cast(T, previous.result)
            if (
                previous is not None
                and previous.state in {"started", "unknown"}
                and not replay_safe
            ):
                raise RenderUnknown("An unconfirmed effect cannot be repeated automatically")
            fresh_intent = previous is None or previous.state not in {"started", "unknown"}
            if fresh_intent:
                await self.checkpoint(stage, "started")
            # A storage await can outlive a feature/permission change. Do not
            # start another protected effect under the request's old decision.
            try:
                current = await self.record()
                node = self.navigation.registry.get(current.node_id)
                params = self.navigation.registry.validate_params(node.id, current.params)
                if fingerprint(params) != fingerprint(current.params):
                    raise InvalidParameters("Prepared parameters cannot be reinterpreted")
                await self.navigation.allowed(self.key, node, params, current.intent.source)
                await self.navigation.authorize_session(self.key, current.session_id)
                await self.record()
            except (AccessDenied, InvalidParameters):
                if fresh_intent:
                    await self.checkpoint(stage, "not_sent")
                raise
            try:
                result = await callback()
            except (TelegramRetryAfter, TelegramBadRequest, TelegramForbiddenError):
                if fresh_intent:
                    await self.checkpoint(stage, "not_sent")
                raise
            except BaseException:
                # Preserve intent even when cancellation prevents this diagnostic write.
                try:
                    await self.checkpoint(stage, "unknown")
                except Exception:
                    pass
                raise
            await self.checkpoint(stage, "confirmed", result)
            return result
