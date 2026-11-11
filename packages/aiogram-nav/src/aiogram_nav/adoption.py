"""Application render adoption fast path, selected before any backend mutation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from .actions import cleanup_committed, complete, prepare
from .effects import normalize_render
from .errors import ConfigurationError, SessionExpired
from .events import emit
from .models import (
    ConversationKey,
    EffectCheckpoint,
    NavigationEvent,
    NavigationIntent,
    NavigationSnapshot,
    RenderRequest,
    RenderResult,
)
from .storage.base import AtomicAdoptionRepository

if TYPE_CHECKING:
    from .navigation import Navigation


async def track(
    nav: Navigation,
    key: ConversationKey,
    node_id: str,
    *,
    rendered: RenderResult,
    operation_id: str,
    params: Mapping[str, object] | None = None,
    source: str = "application",
) -> NavigationSnapshot:
    if nav.draining and nav.coordinator.scope_token(key) is None:
        raise ConfigurationError("Navigation is draining")
    backend = nav.repository if isinstance(nav.repository, AtomicAdoptionRepository) else None
    atomic = backend is not None and getattr(nav.repository, "atomic_adoption", True) is True
    async with nav.coordinator.hold(key):
        if not atomic:
            # Legacy/custom repositories choose this path before preparation. A
            # failed atomic operation is never retried through a different path.
            prepared = await prepare(
                nav,
                key,
                node_id,
                operation_id=operation_id,
                params=params,
                source=source,
                kind="track",
                view_id=rendered.view_id,
            )
            if prepared.status != "completed" and "render" not in prepared.effects:
                await nav.repository.checkpoint(
                    key,
                    operation_id=operation_id,
                    effect=EffectCheckpoint("render", "started"),
                    coordination_scope=nav.coordinator.scope_token(key),
                )
            return (await complete(nav, prepared, rendered)).snapshot
        authority = await nav.authorize_session(key)
        node = nav.registry.get(node_id)
        validated = nav.registry.validate_params(node.id, params)
        await nav.allowed(key, node, validated, source)
        rendered = normalize_render(rendered)
        current = await nav.repository.load(key)
        locale = await nav.locale(key)
        fresh = await nav.authorize_session(key, current.snapshot.session_id if current else None)
        if authority is not None and (
            fresh is None
            or fresh.session_id != authority.session_id
            or fresh.absolute_expires_at != authority.absolute_expires_at
        ):
            raise SessionExpired("Application session changed during render adoption guards")
        intent = NavigationIntent(
            operation_id,
            node.id,
            validated,
            action="track",
            source=source,
            view_id=rendered.view_id,
        )
        assert backend is not None
        result = await backend.adopt_render(
            key,
            expected_version=current.version if current else None,
            intent=intent,
            rendered=rendered,
            coordination_scope=nav.coordinator.scope_token(key),
        )
        if result.duplicate:
            await nav.authorize_session(key, result.snapshot.session_id)
            return result.snapshot
        request = RenderRequest(
            key,
            operation_id,
            node,
            validated,
            result.snapshot.view.view_id,
            result.snapshot.session_id,
            current.snapshot if current else None,
            locale,
            nav.bot,
            nav.dependencies,
            expires_at=result.snapshot.expires_at,
        )
        await emit(
            nav.on_event,
            NavigationEvent(
                operation_id,
                key,
                current.snapshot.node_id if current else None,
                result.snapshot.node_id,
                result.snapshot.nav_revision,
                result.snapshot.activity_revision,
                source,
                "committed",
                nav.clock.now(),
            ),
        )
        await cleanup_committed(nav, key, request, result)
        return result.snapshot
