"""Nav result envelopes reuse the owning idle operation's durable stage ledger."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from hashlib import sha256
from typing import TypeVar, cast

from aiogram_nav.codec import decode, encode
from aiogram_nav.errors import AccessDenied, InvalidParameters
from aiogram_nav.json import fingerprint
from aiogram_nav.models import RenderRequest
from aiogram_nav.navigation import Navigation

from ...effects import OperationEffects
from ...errors import EffectUnknown, OwnershipLost
from ...protocols import EffectRecorder
from .canonical_effects import CanonicalNavigationEffects

T = TypeVar("T")


class NavigationEffects:
    def __init__(
        self, effects: EffectRecorder, navigation: Navigation, request: RenderRequest
    ) -> None:
        self.effects, self.navigation, self.request = effects, navigation, request
        self._scope = navigation.coordinator.scope_token(request.key)
        self._locks: dict[str, asyncio.Lock] = {}
        self._stack: ContextVar[tuple[str, ...]] = ContextVar(
            f"nav_idle_stages_{id(self)}", default=()
        )

    async def run(
        self, stage: str, callback: Callable[[], Awaitable[T]], *, replay_safe: bool = False
    ) -> T:
        literal = f"nav:effect:literal:{stage}"
        full_stage = (
            literal
            if len(literal) <= 128
            else "nav:effect:hash:" + sha256(stage.encode()).hexdigest()
        )
        async with self._serialized(stage):
            recorder = (
                self.effects
                if isinstance(self.effects, (OperationEffects, CanonicalNavigationEffects))
                else None
            )
            fresh = False
            if recorder is not None:
                record = await recorder.record()
                operation = record.idle.operation
                # Record() validates operation ownership.
                assert operation is not None  # nosec B101
                fresh = operation.effects.get(full_stage) not in {"started", "unknown"}

            async def recorded() -> str:
                # The idle recorder verifies session, activity and claim authority;
                # navigation adds authorization immediately before each effect.
                self._owned()
                try:
                    node = self.navigation.registry.get(self.request.node.id)
                    params = self.navigation.registry.validate_params(node.id, self.request.params)
                    if fingerprint(params) != fingerprint(self.request.params):
                        raise InvalidParameters(
                            "Integrated render parameters cannot be reinterpreted"
                        )
                    await self.navigation.allowed(self.request.key, node, params, "idle")
                    self._owned()
                except (AccessDenied, InvalidParameters):
                    if fresh and recorder is not None:
                        # This invocation reserved intent but never called the
                        # application effect. Older uncertainty must stay intact.
                        await recorder.checkpoint(full_stage, "not_sent")
                    raise
                return encode(await callback())

            result = await self.effects.run(full_stage, recorded, replay_safe=replay_safe)
            if not isinstance(cast(object, result), str):
                raise EffectUnknown("Integrated navigation stage result is malformed")
            return cast(T, decode(result))

    @asynccontextmanager
    async def _serialized(self, stage: str) -> AsyncGenerator[None, None]:
        if not stage or len(stage) > 128:
            raise ValueError("Integrated navigation effect stage must be bounded")
        if stage in self._stack.get():
            raise EffectUnknown("Integrated effect stages cannot recursively enter themselves")
        async with self._locks.setdefault(stage, asyncio.Lock()):
            token = self._stack.set((*self._stack.get(), stage))
            try:
                yield
            finally:
                self._stack.reset(token)

    def _owned(self) -> None:
        if self._scope is None or not self.navigation.coordinator.scope_matches(
            self.request.key, self._scope
        ):
            raise OwnershipLost("Integrated render coordination capability ended")
