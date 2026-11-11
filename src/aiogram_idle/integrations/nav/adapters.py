"""Navigation-aware idle actions stage UI changes under the owning idle operation."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from aiogram_nav.codec import decode, encode
from aiogram_nav.errors import AccessDenied
from aiogram_nav.models import PreparedAction, RenderResult
from aiogram_nav.storage.state import fingerprint

from ...errors import ConfigurationError, EffectUnknown
from ...models import ActionReceipt, FlowContext, FlowEligibility
from .effects import NavigationEffects
from .presentation import SILENT_DEPENDENCY

if TYPE_CHECKING:
    from .integration import NavigationIntegration


class NavigationFlowAdapter:
    replay_safe = True

    def __init__(self, integration: NavigationIntegration) -> None:
        self.integration = integration

    async def inspect(self, context: FlowContext) -> FlowEligibility:
        integration = self.integration
        nav = integration.navigation
        if nav is None:
            raise ConfigurationError("Bind Navigation before running the integrated idle worker")
        key = integration.navigation_repository.mapping.to_nav(context.key)
        current = await integration.navigation_repository.load(key)
        if current is None:
            return FlowEligibility(resumable=False, authorized=False)
        snapshot = current.snapshot
        node = nav.registry.resolve(snapshot.node_id)
        try:
            await nav.allowed(key, node, snapshot.params, "idle")
        except AccessDenied:
            return FlowEligibility(
                resumable=False, authorized=False, expires_at=snapshot.expires_at / 1000
            )
        adapter = integration.application_adapter(node.id)
        if adapter is not None:
            eligibility = await adapter.inspect(context)
            return replace(
                eligibility,
                expires_at=min(
                    eligibility.expires_at
                    if eligibility.expires_at is not None
                    else snapshot.expires_at / 1000,
                    snapshot.expires_at / 1000,
                ),
            )
        return FlowEligibility(expires_at=snapshot.expires_at / 1000)

    async def resume(self, context: FlowContext, *, operation_id: str) -> ActionReceipt:
        return await self._render(context, operation_id=operation_id, restore=False)

    async def abandon(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        repo = self.integration.navigation_repository
        current = await repo.load(repo.mapping.to_nav(context.key))
        adapter = (
            self.integration.application_adapter(current.snapshot.node_id) if current else None
        )
        if adapter is not None:
            if context.effects is None:
                raise ConfigurationError(
                    "Business cancellation requires its owning effect recorder"
                )
            return await context.effects.run(
                "nav:business:abandon",
                lambda: adapter.abandon(context, reason=reason, operation_id=operation_id),
                replay_safe=getattr(adapter, "replay_safe", False) is True,
            )
        return ActionReceipt(operation_id, "disarm")

    async def restore(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        return await self._render(context, operation_id=operation_id, restore=True)

    async def _render(
        self, context: FlowContext, *, operation_id: str, restore: bool
    ) -> ActionReceipt:
        integration = self.integration
        nav = integration.navigation
        effects = context.effects
        if nav is None or effects is None:
            raise ConfigurationError(
                "Integrated navigation action needs its owning operation recorder"
            )
        repo = integration.navigation_repository
        current = await repo.load(repo.mapping.to_nav(context.key))
        if current is None:
            raise EffectUnknown("Integrated navigation screen is no longer retained")
        current_node = nav.registry.resolve(current.snapshot.node_id)
        target = nav.registry.cancel_target(current_node.id) if restore else current_node.id
        async with repo.staging(context):

            async def prepare() -> str:
                return encode(await repo.prepare_staged(context, target, operation_id=operation_id))

            raw = await effects.run("nav:prepare", prepare, replay_safe=True)
            if not isinstance(cast(object, raw), str) or not isinstance(
                prepared := decode(raw), PreparedAction
            ):
                raise EffectUnknown("Integrated render reservation is malformed")
            canonical = await repo.pending(repo.mapping.to_nav(context.key))
            if (
                canonical is None
                or prepared.key != repo.mapping.to_nav(context.key)
                or prepared.operation_id != operation_id
                or prepared.session_id != context.activity.session_id
                or prepared.node_id != target
                or prepared.fingerprint != canonical.fingerprint
                or fingerprint(prepared.intent) != canonical.fingerprint
                or any(
                    getattr(prepared, name) != getattr(canonical, name)
                    for name in ("key", "session_id", "view_id", "expires_at", "expected_version")
                )
            ):
                # Resume and restore share one reserved idle operation. A cached
                # preparation from a previous route cannot authorize a different
                # destination or another conversation's external effects.
                raise EffectUnknown("Cached navigation reservation no longer matches this action")
            prepared = canonical
            request = await nav.request(prepared)
            owner = await integration.idle.backend.load(context.key)
            if (
                request.current is not None
                and owner is not None
                and owner.idle.prompt is not None
                and owner.idle.prompt.controls in {"reply", "hybrid"}
            ):
                # The prompt installed a different reply tray. A matching old
                # semantic key no longer proves that the screen's tray is live.
                request = replace(
                    request,
                    current=replace(
                        request.current,
                        view=replace(
                            request.current.view,
                            reply_keyboard_key=None,
                            reply_keyboard_locale=None,
                        ),
                    ),
                )
            render_effects = effects
            canonical_mode = getattr(repo.idle.backend, "active_storage_format", 1) == 3
            if canonical_mode:
                from ...effects import OperationEffects
                from .canonical_effects import CanonicalNavigationEffects

                if not isinstance(effects, OperationEffects):
                    raise ConfigurationError(
                        "Canonical UI recovery requires the owning idle effect recorder"
                    )
                render_effects = CanonicalNavigationEffects(
                    effects, repo, request.key, prepared.operation_id
                )
            bridge = NavigationEffects(render_effects, nav, request)
            request = replace(
                request,
                effects=bridge,
                delivery="send",
                dependencies={
                    **request.dependencies,
                    **context.dependencies,
                    **({SILENT_DEPENDENCY: True} if restore else {}),
                },
            )

            async def render() -> str:
                result = await nav.presenter.render(request)
                from aiogram_nav.actions import validate_render

                validate_render(prepared, result)
                return encode(result)

            if canonical_mode:

                async def canonical_render() -> RenderResult:
                    result = await nav.presenter.render(request)
                    from aiogram_nav.actions import validate_render

                    validate_render(prepared, result)
                    return result

                rendered = await render_effects.run(
                    "render",
                    canonical_render,
                    replay_safe=getattr(nav.presenter, "replay_safe", False) is True,
                )
            else:
                raw_rendered = await effects.run(
                    "nav:render",
                    render,
                    replay_safe=getattr(nav.presenter, "replay_safe", False) is True,
                )
                if not isinstance(cast(object, raw_rendered), str) or not isinstance(
                    rendered := decode(raw_rendered), RenderResult
                ):
                    raise EffectUnknown("Integrated render receipt is malformed")
            return await repo.stage(
                context,
                prepared,
                rendered,
                operation_id=operation_id,
                disposition="replacement" if restore else "rearm",
            )
