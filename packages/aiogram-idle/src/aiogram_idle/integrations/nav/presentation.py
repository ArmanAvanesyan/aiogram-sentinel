"""Reconstruct a navigation reply tray after a temporary idle overlay."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from aiogram import Bot
from aiogram.types import ReplyKeyboardRemove
from aiogram_nav.models import RenderRequest, RenderResult
from aiogram_nav.rendering.base import (
    CleanupRequest,
    CleanupResult,
    NavigationPresenter,
    ScreenSpec,
)
from aiogram_nav.rendering.text import Renderer, TextPresenter

from ...errors import ConfigurationError, OwnershipLost
from .codec import COMPONENT

if TYPE_CHECKING:
    from .integration import NavigationIntegration

OVERLAY_DEPENDENCY = "aiogram_idle.reply_overlay"
SILENT_DEPENDENCY = "aiogram_idle.silent_restore"


class NavigationPresentation:
    """Standalone presentation is unchanged; only a proven idle overlay is reset."""

    def __init__(self, integration: NavigationIntegration, original: NavigationPresenter) -> None:
        self.integration, self.original = integration, original

    @property
    def bot(self) -> Bot | None:
        value = getattr(self.original, "bot", None)
        return value if isinstance(value, Bot) else None

    @property
    def replay_safe(self) -> bool:
        return getattr(self.original, "replay_safe", False) is True

    def __getattr__(self, name: str) -> Any:
        return getattr(self.original, name)

    async def render(self, request: RenderRequest) -> RenderResult:
        repo = self.integration.navigation_repository
        scope = repo.coordinator.scope_token(request.key)
        current = await self.integration.idle.backend.load(repo.mapping.to_idle(request.key))
        body = current.components.get(COMPONENT) if current else None
        overlaid = (isinstance(body, Mapping) and body.get("reply_overlay") is True) or (
            current is not None
            and current.idle.prompt is not None
            and current.idle.prompt.controls in {"reply", "hybrid"}
        )
        if scope is None or not repo.coordinator.scope_matches(request.key, scope):
            raise OwnershipLost("Navigation presentation coordination ended")
        silent_restore = request.dependencies.get(SILENT_DEPENDENCY) is True
        if not overlaid and not silent_restore:
            return await self.original.render(request)
        if overlaid and request.current is not None:
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
        if overlaid:
            request = replace(
                request, dependencies={**request.dependencies, OVERLAY_DEPENDENCY: True}
            )
        if type(self.original) is not TextPresenter:
            # Custom presenters own reconstruction and receive the explicit
            # overlay signal alongside invalidated tray provenance.
            return await self.original.render(request)
        original = cast(TextPresenter, self.original)
        renderer_key = request.node.renderer
        if renderer_key is None or renderer_key not in original.renderers:
            raise ConfigurationError("The target navigation renderer is unavailable")
        original_renderer: Renderer = original.renderers[renderer_key]

        async def screen(inner: RenderRequest) -> ScreenSpec:
            spec = await original_renderer(inner)
            if not isinstance(cast(object, spec), ScreenSpec):
                return spec
            if silent_restore:
                spec = replace(spec, silent=True)
            if overlaid and spec.reply_keyboard is None:
                # Omission means keep in standalone navigation. Keeping here
                # would leave the prompt's Continue/Cancel tray installed.
                return replace(spec, reply_keyboard=ReplyKeyboardRemove(), reply_keyboard_key=None)
            return spec

        presenter = TextPresenter({**original.renderers, renderer_key: screen}, original.bot)
        return await presenter.render(request)

    async def cleanup(self, request: CleanupRequest) -> CleanupResult:
        return await self.original.cleanup(request)
