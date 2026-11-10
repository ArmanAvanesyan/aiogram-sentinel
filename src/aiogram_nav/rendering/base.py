"""Restricted text plans and generation-specific cleanup contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from ..errors import ConfigurationError
from ..models import ConversationKey, MessageRef, RenderRequest, RenderResult, ViewState


@dataclass(frozen=True)
class ScreenSpec:
    text: str
    inline_keyboard: InlineKeyboardMarkup | None = None
    reply_keyboard: ReplyKeyboardMarkup | ReplyKeyboardRemove | None = None
    reply_keyboard_key: str | None = None
    delivery: Literal["auto", "send", "edit"] = "auto"
    tray_text: str = "Choose an action."
    parse_mode: Literal["HTML", "Markdown", "MarkdownV2"] | None = None
    silent: bool = False

    def __post_init__(self) -> None:
        for name in ("text", "tray_text"):
            value = cast(object, getattr(self, name))
            if not isinstance(value, str) or not value or len(value) > 4096:
                raise ConfigurationError("Screen and tray text must contain 1 to 4096 characters")
        if self.delivery not in ("auto", "send", "edit"):
            raise ConfigurationError("Unknown text delivery preference")
        if self.parse_mode not in (None, "HTML", "Markdown", "MarkdownV2"):
            raise ConfigurationError("Unsupported text parse mode")
        if not isinstance(cast(object, self.silent), bool):
            raise ConfigurationError("Silent delivery must be a boolean")
        if self.inline_keyboard is not None and not isinstance(
            cast(object, self.inline_keyboard), InlineKeyboardMarkup
        ):
            raise ConfigurationError("Inline markup must be InlineKeyboardMarkup")
        if self.reply_keyboard is not None and not isinstance(
            cast(object, self.reply_keyboard), (ReplyKeyboardMarkup, ReplyKeyboardRemove)
        ):
            raise ConfigurationError("Reply markup must be a keyboard or explicit removal")
        if isinstance(self.reply_keyboard, ReplyKeyboardMarkup):
            key = cast(object, self.reply_keyboard_key)
            if not isinstance(key, str) or not key or len(key) > 256:
                raise ConfigurationError("Reply keyboards require a semantic key")
        elif self.reply_keyboard_key is not None:
            raise ConfigurationError("A keyboard key requires a reply keyboard")
        for name in ("inline_keyboard", "reply_keyboard"):
            markup = getattr(self, name)
            if markup is not None:
                object.__setattr__(self, name, markup.model_copy(deep=True))


@dataclass(frozen=True)
class CleanupRequest:
    key: ConversationKey
    previous: ViewState | None
    current: ViewState | None
    bot: Bot | None = None
    # Custom presenters must call this immediately before each new external effect.
    ensure_owned: Callable[[], None] | None = None


@dataclass(frozen=True)
class CleanupResult:
    messages: tuple[MessageRef, ...] = ()
    unavailable: bool = False


class NavigationPresenter(Protocol):
    async def render(self, request: RenderRequest) -> RenderResult: ...
    async def cleanup(self, request: CleanupRequest) -> CleanupResult: ...
