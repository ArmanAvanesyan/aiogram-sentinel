"""One authorized prepare/effect/complete path for every navigation transport."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from .effects import NavigationEffects, normalize_render
from .errors import (
    AccessDenied,
    ConfigurationError,
    InvalidParameters,
    NavigationError,
    NodeNotFound,
    OperationIdConflict,
    OwnershipLost,
    RenderUnknown,
    StaleView,
)
from .events import emit
from .json import fingerprint
from .models import (
    ActionKind,
    CommitResult,
    ConversationKey,
    EffectCheckpoint,
    HistoryMode,
    NavigationEvent,
    NavigationIntent,
    NavigationMutation,
    NavigationSnapshot,
    PreparedAction,
    RenderRequest,
    RenderResult,
    ViewState,
)
from .rendering.base import CleanupRequest

if TYPE_CHECKING:
    from .navigation import Navigation


def as_render(snapshot: NavigationSnapshot) -> RenderResult:
    view = snapshot.view
    return RenderResult(
        view.view_id,
        view.messages,
        view.reply_keyboard_key,
        view.locale,
        view.reply_keyboard_locale,
    )


def root_target(nav: Navigation, current: NavigationSnapshot | None) -> str:
    if current is not None:
        return nav.registry.root_for(nav.registry.resolve(current.node_id).id)
    if nav.config.root is not None:
        return nav.config.root
    if len(nav.registry.roots) == 1:
        return next(iter(nav.registry.roots))
    raise ConfigurationError("Select an explicit root when the registry has multiple roots")


async def prepare(
    nav: Navigation,
    key: ConversationKey,
    node_id: str,
    *,
    operation_id: str,
    params: Mapping[str, object] | None = None,
    source: str = "application",
    kind: ActionKind = "go",
    history: HistoryMode = "push",
    accepted_activity: bool = True,
    view_id: str | None = None,
    history_pop: int = 1,
) -> PreparedAction:
    await nav.authorize_session(key)
    node = nav.registry.get(node_id)
    validated = nav.registry.validate_params(node.id, params)
    await nav.allowed(key, node, validated, source)
    loaded = await nav.repository.load(key)
    intent = NavigationIntent(
        operation_id,
        node.id,
        validated,
        action=kind,
        history=history,
        source=source,
        accepted_activity=accepted_activity,
        view_id=view_id,
        history_pop=history_pop,
    )
    return await nav.repository.prepare(
        key,
        expected_version=loaded.version if loaded else None,
        intent=intent,
        coordination_scope=nav.coordinator.scope_token(key),
    )


async def target(
    nav: Navigation,
    key: ConversationKey,
    kind: ActionKind,
    current: NavigationSnapshot | None,
    requested: str | None,
    params: Mapping[str, object] | None,
    history: HistoryMode,
    source: str,
) -> tuple[str, Mapping[str, object] | None, HistoryMode, int]:
    if kind in {"go", "track"}:
        if requested is None:
            raise NodeNotFound("An explicit destination is required")
        return requested, params, history, 1
    if kind == "home":
        destination = requested or root_target(nav, current)
        if destination not in nav.registry.roots:
            raise ConfigurationError("home requires an explicitly configured root")
        return destination, {}, "clear", 1
    if current is None:
        return root_target(nav, current), {}, "none", 1
    node = nav.registry.resolve(current.node_id)
    if kind == "refresh":
        preserved = (
            current.node_id in nav.registry.nodes or current.node_id in nav.registry.migrations
        )
        return node.id, current.params if preserved else {}, "none", 1
    if kind == "cancel":
        return nav.registry.cancel_target(node.id), {}, "clear", 1
    if node.id in nav.registry.roots:
        return node.id, current.params, "none", 1
    back = nav.registry.back_target(node.id)
    if back is not None:
        return back, {}, "pop", 1
    for count, entry in enumerate(reversed(current.history), 1):
        try:
            old = nav.registry.resolve(entry.node_id)
            if nav.registry.root_for(old.id) != nav.registry.root_for(node.id):
                continue
            preserved = (
                entry.node_id in nav.registry.nodes or entry.node_id in nav.registry.migrations
            )
            validated = nav.registry.validate_params(old.id, entry.params if preserved else {})
            await nav.allowed(key, old, validated, source)
        except (NodeNotFound, InvalidParameters, AccessDenied):
            continue
        return old.id, validated, "pop", count
    return root_target(nav, current), {}, "clear", 1


def retry_matches(
    prepared: PreparedAction,
    kind: ActionKind,
    requested: str | None,
    params: Mapping[str, object] | None,
    history: HistoryMode,
    source: str,
    accepted_activity: bool,
    nav: Navigation,
) -> None:
    intent = prepared.intent
    if (
        intent.action != kind
        or intent.source != source
        or intent.accepted_activity != accepted_activity
    ):
        raise OperationIdConflict("Operation ID belongs to a different navigation request")
    if kind in {"go", "track"}:
        if (
            intent.node_id != requested
            or fingerprint(intent.params)
            != fingerprint(nav.registry.validate_params(intent.node_id, params))
            or intent.history != history
        ):
            raise OperationIdConflict("Operation ID belongs to different navigation parameters")
    if kind == "home" and requested is not None and requested != intent.node_id:
        raise OperationIdConflict("Operation ID belongs to another home target")


async def prepare_action(
    nav: Navigation,
    key: ConversationKey,
    kind: ActionKind,
    *,
    operation_id: str,
    node_id: str | None = None,
    params: Mapping[str, object] | None = None,
    history: HistoryMode = "push",
    source: str = "application",
    accepted_activity: bool = True,
) -> PreparedAction:
    if type(accepted_activity) is not bool:
        raise ConfigurationError("accepted_activity must be a boolean")
    async with nav.coordinator.hold(key):
        await nav.authorize_session(key)
        existing = await nav.repository.lookup_operation(key, operation_id=operation_id)
        if existing.prepared is not None:
            prepared = existing.prepared
            await nav.authorize_session(key, prepared.session_id)
            retry_matches(prepared, kind, node_id, params, history, source, accepted_activity, nav)
            await nav.allowed(key, nav.registry.get(prepared.node_id), prepared.params, source)
            if existing.result is not None:
                return prepared
            return prepared
        loaded = await nav.repository.load(key)
        current = loaded.snapshot if loaded else None
        pending = await nav.repository.pending(key)
        if kind == "refresh" and pending is not None:
            cancellation = pending.effects.get("cancel")
            if cancellation is not None and cancellation.state in {"started", "unknown"}:
                raise RenderUnknown("Unknown business cancellation requires explicit recovery")
            if cancellation is not None and cancellation.state == "confirmed":
                node_id, params = pending.node_id, pending.params
        if kind == "refresh" and node_id is not None:
            destination, values, mode, count = node_id, params, "none", 1
        else:
            destination, values, mode, count = await target(
                nav, key, kind, current, node_id, params, history, source
            )
        if kind == "refresh" and pending is not None:
            validated = nav.registry.validate_params(destination, values)
            await nav.allowed(key, nav.registry.get(destination), validated, source)
            await nav.repository.abandon(
                key, pending.operation_id, expected_session_id=pending.session_id
            )
        prepared = await prepare(
            nav,
            key,
            destination,
            operation_id=operation_id,
            params=values,
            source=source,
            kind=kind,
            history=mode,
            accepted_activity=accepted_activity,
            history_pop=count,
        )
        return prepared


async def perform(
    nav: Navigation,
    key: ConversationKey,
    kind: ActionKind,
    *,
    operation_id: str,
    node_id: str | None = None,
    params: Mapping[str, object] | None = None,
    history: HistoryMode = "push",
    source: str = "application",
    accepted_activity: bool = True,
) -> RenderResult:
    async with nav.coordinator.hold(key):
        prepared = await prepare_action(
            nav,
            key,
            kind,
            operation_id=operation_id,
            node_id=node_id,
            params=params,
            history=history,
            source=source,
            accepted_activity=accepted_activity,
        )
        status = await nav.repository.lookup_operation(key, operation_id=operation_id)
        if status.result is not None:
            return as_render(status.result.snapshot)
        return await execute(nav, prepared)


def validate_render(prepared: PreparedAction, rendered: RenderResult) -> None:
    if isinstance(rendered, ViewState) and rendered.render_status != "complete":
        raise RenderUnknown("Partial rendering cannot complete a navigation action")
    if rendered.view_id != prepared.view_id or any(
        ref.chat_id != prepared.key.chat_id for ref in rendered.messages
    ):
        raise StaleView("Render receipt does not match the prepared conversation/view")


async def execute(nav: Navigation, prepared: PreparedAction) -> RenderResult:
    effects = NavigationEffects(nav, prepared)
    request = await nav.request(prepared, effects=effects)
    if (
        prepared.intent.action == "cancel"
        and nav.cancel_hook is not None
        and request.current is not None
    ):

        async def cancel() -> object:
            try:
                return await nav.cancel_hook(request)  # type: ignore[misc]
            except Exception as error:
                raise RenderUnknown("Cancellation outcome requires recovery") from error

        await effects.run(
            "cancel", cancel, replay_safe=getattr(nav.cancel_hook, "replay_safe", False) is True
        )
    replay_safe = getattr(nav.presenter, "replay_safe", False) is True

    async def render() -> RenderResult:
        try:
            result = await nav.presenter.render(request)
        except Exception as error:
            if not replay_safe:
                raise RenderUnknown("Custom presenter outcome requires recovery") from error
            raise
        validate_render(prepared, result)
        return normalize_render(result)

    try:
        rendered = await effects.run("render", render, replay_safe=replay_safe)
        validate_render(prepared, rendered)
        await complete(nav, prepared, rendered)
    except NavigationError:
        raise
    except Exception as error:
        raise RenderUnknown("Rendering did not complete; inspect the retained action") from error
    return rendered


async def cleanup_committed(
    nav: Navigation, prepared: PreparedAction, request: RenderRequest, committed: CommitResult
) -> None:
    previous = request.current.view if request.current else None
    scope = nav.coordinator.scope_token(prepared.key)
    if scope is None or not nav.coordinator.scope_matches(prepared.key, scope):
        # A slow observational hook can outlive its lease. The committed result
        # remains valid, but lost ownership cannot authorize another Telegram call.
        return
    try:
        latest = await nav.repository.load(prepared.key)
        if (
            latest is None
            or latest.snapshot.session_id != committed.snapshot.session_id
            or latest.snapshot.view.view_id != committed.snapshot.view.view_id
        ):
            # An observational hook may navigate reentrantly under this same lock.
            return

        await nav.authorize_session(prepared.key, committed.snapshot.session_id)

        def ensure_owned() -> None:
            if not nav.coordinator.scope_matches(prepared.key, scope):
                raise OwnershipLost("Post-commit cleanup ownership expired")

        ensure_owned()
        await nav.presenter.cleanup(
            CleanupRequest(prepared.key, previous, committed.snapshot.view, nav.bot, ensure_owned)
        )
    except Exception:
        from .navigation import logger

        logger.warning("Generation-specific navigation cleanup failed after commit")
    return


async def complete(
    nav: Navigation, prepared: PreparedAction, rendered: RenderResult
) -> CommitResult:
    validate_render(prepared, rendered)
    rendered = normalize_render(rendered)
    status = await nav.repository.lookup_operation(prepared.key, operation_id=prepared.operation_id)
    canonical = status.prepared
    if (
        canonical is None
        or canonical.fingerprint != prepared.fingerprint
        or canonical.intent != prepared.intent
        or fingerprint(canonical.params) != fingerprint(prepared.params)
        or canonical.session_id != prepared.session_id
        or canonical.view_id != prepared.view_id
        or canonical.key != prepared.key
    ):
        raise StaleView("The prepared action is no longer retained or its identity changed")
    prepared = canonical
    if status.result is not None:
        await nav.authorize_session(prepared.key, prepared.session_id)
        if as_render(status.result.snapshot) != rendered:
            raise OperationIdConflict("Completion receipt differs from the retained result")
        return replace(status.result, duplicate=True)
    # Recording an already known send is not a new external effect. Keep that
    # evidence even if application authority was revoked before completion.
    await nav.repository.checkpoint(
        prepared.key,
        operation_id=prepared.operation_id,
        effect=EffectCheckpoint("render", "confirmed", rendered),
        coordination_scope=nav.coordinator.scope_token(prepared.key),
    )
    request = await nav.request(prepared)
    if (
        prepared.intent.action == "cancel"
        and nav.cancel_hook is not None
        and request.current is not None
    ):
        effects = NavigationEffects(nav, prepared)

        async def cancel() -> object:
            if nav.cancel_hook is None:
                return None
            return await nav.cancel_hook(request)

        await effects.run(
            "cancel", cancel, replay_safe=getattr(nav.cancel_hook, "replay_safe", False) is True
        )
    loaded = await nav.repository.load(prepared.key)
    committed = await nav.repository.commit(
        prepared.key,
        expected_version=loaded.version if loaded else None,
        mutation=NavigationMutation(
            prepared.operation_id,
            prepared.session_id,
            rendered,
            accepted_activity=prepared.intent.accepted_activity,
            source=prepared.intent.source,
        ),
        coordination_scope=nav.coordinator.scope_token(prepared.key),
    )
    if not committed.duplicate:
        await emit(
            nav.on_event,
            NavigationEvent(
                prepared.operation_id,
                prepared.key,
                request.current.node_id if request.current else None,
                committed.snapshot.node_id,
                committed.snapshot.nav_revision,
                committed.snapshot.activity_revision,
                prepared.intent.source,
                "committed",
                nav.clock.now(),
            ),
        )
    if not committed.duplicate:
        await cleanup_committed(nav, prepared, request, committed)
    return committed
