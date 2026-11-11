"""
Apply full configurations to Telegram bot.
"""

import json
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    MenuButtonCommands,
    MenuButtonDefault,
)

from .builders_configured import build_from_config
from .customize import CmdsConfig
from .delivery import CommandBatchResult
from .engines import Engine, native_engine
from .registry import CommandRegistry
from .scopes import ScopeObject
from .scopes import scope_object as _scope_obj
from .scopes import sorted_scopes as _sorted_scopes
from .translator import Translator

if TYPE_CHECKING:
    from .compiled import CompiledCommands


def _targets(
    cfg: CmdsConfig, translator: Translator | None
) -> list[tuple[ScopeObject, str | None, list[BotCommand]]]:
    reg = CommandRegistry(cfg)
    targets: list[tuple[ScopeObject, str | None, list[BotCommand]]] = []
    for scope in _sorted_scopes(cfg.scopes):
        scope_obj = _scope_obj(scope)
        languages = scope.languages or cfg.languages or ["en"]
        per_language = (
            cfg.per_language if scope.per_language is None else scope.per_language
        )
        for language in languages if per_language else languages[:1]:
            commands = build_from_config(
                reg,
                list(reg.resolve_profile_commands(scope.profile)),
                lang=language,
                translator=translator,
                key_prefix=cfg.i18n_key_prefix,
            )
            targets.append((scope_obj, language if per_language else None, commands))
    return targets


async def apply_config(
    bot: Bot, cfg: CmdsConfig, *, translator: Translator | None = None
) -> None:
    """Apply all configured scopes and menu button; original failures propagate.

    This is not a Telegram transaction. Earlier successful targets remain applied
    if a later request fails. Use apply_config_result for explicit partial results.
    """
    await apply_config_result(bot, cfg, translator=translator)


async def apply_config_result(
    bot: Bot,
    cfg: CmdsConfig,
    *,
    translator: Translator | None = None,
    best_effort: bool = False,
    compiled: "CompiledCommands | None" = None,
    engine: Engine = "python",
) -> CommandBatchResult:
    """Apply prepared targets with optional partial-completion evidence."""
    native_engine(engine)
    if type(best_effort) is not bool:
        raise TypeError("best_effort must be a boolean")
    completed: list[str] = []
    target = "configuration"
    try:
        # Validate/render all scopes before performing the first network effect.
        for scope, slot, commands in (
            compiled.targets() if compiled is not None else _targets(cfg, translator)
        ):
            target = json.dumps(
                {"scope": scope.model_dump(exclude_none=True), "language_code": slot},
                sort_keys=True,
                separators=(",", ":"),
            )
            if slot is None:
                response = await bot.set_my_commands(commands, scope=scope)
            else:
                response = await bot.set_my_commands(
                    commands, scope=scope, language_code=slot
                )
            if response is not True:
                raise RuntimeError("Telegram did not apply the command menu")
            completed.append(target)
        target = "menu_button"
        if cfg.menu_button.mode == "commands":
            response = await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        else:
            response = await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
        if response is not True:
            raise RuntimeError("Telegram did not apply the menu button")
        completed.append(target)
    except Exception as error:
        if not best_effort:
            raise
        return CommandBatchResult(
            "partial" if completed else "failed", tuple(completed), target, error
        )
    return CommandBatchResult("applied", tuple(completed))
