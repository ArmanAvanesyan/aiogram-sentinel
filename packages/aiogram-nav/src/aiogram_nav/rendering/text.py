"""Text-only optional presenter with a checkpointed, immutable presentation plan."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import ClassVar, Literal, cast

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from ..errors import ConfigurationError
from ..json import JsonObject, freeze_object
from ..models import RenderRequest, RenderResult
from .base import CleanupRequest, CleanupResult, ScreenSpec
from .cleanup import cleanup_inline
from .delivery import deliver

Renderer = Callable[[RenderRequest], Awaitable[ScreenSpec]]


class TextPresenter:
    replay_safe: ClassVar[bool] = True

    def __init__(self, renderers: Mapping[str, Renderer], bot: Bot | None = None) -> None:
        self.renderers = MappingProxyType(dict(renderers))
        self.bot = bot

    @property
    def renderer_keys(self) -> frozenset[str]:
        return frozenset(self.renderers)

    async def render(self, request: RenderRequest) -> RenderResult:
        effects = request.effects
        if effects is None:
            raise ConfigurationError("Text presentation requires a prepared effect recorder")
        renderer_key = request.node.renderer
        if renderer_key is None or renderer_key not in self.renderers:
            raise ConfigurationError("The target text renderer is unavailable")

        async def plan() -> JsonObject:
            spec = await self.renderers[renderer_key](request)
            if not isinstance(cast(object, spec), ScreenSpec):
                raise ConfigurationError("Text renderers must return ScreenSpec")
            return freeze_object(
                {
                    "locale": request.locale,
                    "text": spec.text,
                    "inline": spec.inline_keyboard.model_dump(mode="json", exclude_none=True)
                    if spec.inline_keyboard is not None
                    else None,
                    "reply": spec.reply_keyboard.model_dump(mode="json", exclude_none=True)
                    if spec.reply_keyboard is not None
                    else None,
                    "reply_kind": "remove"
                    if isinstance(spec.reply_keyboard, ReplyKeyboardRemove)
                    else "keyboard"
                    if isinstance(spec.reply_keyboard, ReplyKeyboardMarkup)
                    else "keep",
                    "reply_key": spec.reply_keyboard_key,
                    "delivery": spec.delivery,
                    "tray_text": spec.tray_text,
                    "parse_mode": spec.parse_mode,
                    "silent": spec.silent,
                },
                max_bytes=65_536,
            )

        saved = await effects.run("text.plan", plan, replay_safe=True)
        from ..json import thaw_json

        data = thaw_json(saved)
        if not isinstance(data, dict):
            raise ConfigurationError("The recorded text plan is malformed")
        recorded = cast(dict[str, object], data)
        spec = _restore(recorded)
        locale = recorded.get("locale")
        if not isinstance(locale, str) or not locale or len(locale) > 256:
            raise ConfigurationError("The recorded text locale is malformed")
        return await deliver(replace(request, locale=locale), spec, self.bot)

    async def cleanup(self, request: CleanupRequest) -> CleanupResult:
        return await cleanup_inline(request, self.bot)


def _restore(data: dict[str, object]) -> ScreenSpec:
    if set(data) != {
        "locale",
        "text",
        "inline",
        "reply",
        "reply_kind",
        "reply_key",
        "delivery",
        "tray_text",
        "parse_mode",
        "silent",
    }:
        raise ConfigurationError("The recorded text plan is malformed")
    if data["reply_kind"] not in ("keyboard", "remove", "keep"):
        raise ConfigurationError("The recorded reply plan is unsupported")
    if data["reply_kind"] == "keep" and data["reply"] is not None:
        raise ConfigurationError("A keep-reply plan cannot contain replacement markup")
    inline = (
        InlineKeyboardMarkup.model_validate(data["inline"]) if data["inline"] is not None else None
    )
    reply = (
        ReplyKeyboardMarkup.model_validate(data["reply"])
        if data["reply_kind"] == "keyboard"
        else ReplyKeyboardRemove.model_validate(data["reply"])
        if data["reply_kind"] == "remove"
        else None
    )
    # Validation is repeated on recovery; a bad stored plan cannot produce effects.
    return ScreenSpec(
        text=cast(str, data["text"]),
        inline_keyboard=inline,
        reply_keyboard=reply,
        reply_keyboard_key=cast(str | None, data["reply_key"]),
        delivery=cast(Literal["auto", "send", "edit"], data["delivery"]),
        tray_text=cast(str, data["tray_text"]),
        parse_mode=cast(Literal["HTML", "Markdown", "MarkdownV2"] | None, data["parse_mode"]),
        silent=cast(bool, data["silent"]),
    )
