"""Bounded action classification and explicit application spam exemptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from aiogram.types import CallbackQuery, Message, TelegramObject

from .exceptions import ConfigurationError
from .policy import DebounceCfg, ThrottleCfg

ActionKind = Literal["message", "command", "callback_query"]


@dataclass(frozen=True)
class ActionPolicy:
    """Per-kind defaults; ``None`` inherits the global value for that protection."""

    throttle: ThrottleCfg | None = None
    debounce: DebounceCfg | None = None

    def __post_init__(self) -> None:
        if self.throttle is not None and not isinstance(
            cast(object, self.throttle), ThrottleCfg
        ):
            raise ConfigurationError("Action throttle must be a ThrottleCfg")
        if self.debounce is not None and not isinstance(
            cast(object, self.debounce), DebounceCfg
        ):
            raise ConfigurationError("Action debounce must be a DebounceCfg")


def command_name(event: TelegramObject) -> str | None:
    """Recognize an initial Telegram command entity, including bot suffixes."""
    if not isinstance(event, Message) or not event.text:
        return None
    for entity in event.entities or ():
        if entity.type == "bot_command" and entity.offset == 0:
            # Telegram offsets/lengths are UTF-16, not Python character positions.
            command = event.text.encode("utf-16-le")[: entity.length * 2].decode(
                "utf-16-le", errors="replace"
            )
            return command.removeprefix("/").split("@", 1)[0].casefold()
    return None


def classify_action(event: TelegramObject) -> ActionKind:
    if isinstance(event, CallbackQuery):
        return "callback_query"
    return "command" if command_name(event) is not None else "message"


@dataclass(frozen=True)
class SentinelExemptions:
    """Opt-in spam bypasses; these never bypass application middleware."""

    commands: tuple[str, ...] = ()
    callback_prefixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.commands), (tuple, list)) or not isinstance(
            cast(object, self.callback_prefixes), (tuple, list)
        ):
            raise ConfigurationError("Exempt commands and prefixes must be sequences")
        commands = tuple(self.commands)
        prefixes = tuple(self.callback_prefixes)
        if any(
            not isinstance(cast(object, value), str)
            or not value
            or len(value) > 32
            or any(
                not (char.isascii() and (char.isalnum() or char == "_"))
                for char in value
            )
            for value in commands
        ):
            raise ConfigurationError("Exempt commands use bare Telegram command names")
        if any(
            not isinstance(cast(object, value), str)
            or not value
            or len(value.encode()) > 64
            for value in prefixes
        ):
            raise ConfigurationError("Exempt callback prefixes contain 1 to 64 bytes")
        object.__setattr__(
            self, "commands", tuple(value.casefold() for value in commands)
        )
        object.__setattr__(self, "callback_prefixes", prefixes)

    def matches(self, event: TelegramObject) -> bool:
        if isinstance(event, CallbackQuery):
            return bool(event.data) and event.data.startswith(self.callback_prefixes)
        return command_name(event) in self.commands
