"""Weakly retained stage locks shared by recorders in one coordination scope."""

import asyncio
from contextvars import ContextVar
from weakref import WeakValueDictionary


class EffectScope:
    def __init__(self) -> None:
        self.stages: dict[str, asyncio.Lock] = {}
        self.checkpoint = asyncio.Lock()
        self.active: set[object] = set()


_scopes: WeakValueDictionary[tuple[int, int, object, str], EffectScope] = WeakValueDictionary()
stack: ContextVar[tuple[tuple[EffectScope, str, object], ...]] = ContextVar(
    "idle_effect_scope_stack", default=()
)


def scope_for(coordinator: object, token: object, key: object, operation: str) -> EffectScope:
    identity = (id(coordinator), id(token), key, operation)
    scope = _scopes.get(identity)
    if scope is None:
        scope = EffectScope()
        _scopes[identity] = scope
    return scope
