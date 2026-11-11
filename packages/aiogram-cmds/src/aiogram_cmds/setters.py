"""
Simple (classic) setters for per-user and global scopes.
"""

import logging
from collections.abc import Iterable

from aiogram import Bot
from aiogram.types import (
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    MenuButtonCommands,
    MenuButtonDefault,
)

from .builder import build_bot_commands
from .delivery import UNSET, LanguageCode, menu_slot
from .policy import CommandPolicy, Flags, default_policy
from .translator import Translator

logger = logging.getLogger(__name__)


async def set_user_commands_by_flags(
    bot: Bot,
    user_id: int,
    *,
    is_registered: bool,
    has_vehicle: bool,
    is_during_registration: bool = False,
    user_language: str = "en",
    policy: CommandPolicy = default_policy,
    translator: Translator | None = None,
    key_prefix: str = "cmd",
    language_code: str | None | LanguageCode = UNSET,
) -> None:
    names = policy(
        Flags(
            is_registered=is_registered,
            has_vehicle=has_vehicle,
            is_during_registration=is_during_registration,
        )
    )
    commands = build_bot_commands(
        names, lang=user_language, translator=translator, key_prefix=key_prefix
    )
    # Per-chat override (user's private chat)
    slot = menu_slot(user_language, language_code)
    if slot is None:
        response = await bot.set_my_commands(
            commands=commands, scope=BotCommandScopeChat(chat_id=user_id)
        )
    else:
        response = await bot.set_my_commands(
            commands=commands,
            scope=BotCommandScopeChat(chat_id=user_id),
            language_code=slot,
        )
    if response is not True:
        raise RuntimeError("Telegram did not apply the command menu")


async def clear_user_commands(bot: Bot, user_id: int) -> None:
    # Delete per-chat override (falls back to broader scopes)
    if (
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))
        is not True
    ):
        raise RuntimeError("Telegram did not delete the command menu")


async def setup_all_command_scopes(
    bot: Bot,
    *,
    languages: tuple[str, ...],
    translator: Translator | None = None,
    key_prefix: str = "cmd",
    menu_button: str = "commands",
    default_commands: Iterable[str] | None = None,
) -> None:
    """
    Configure default/global command sets and the menu button for classic mode.
    """
    base_names = list(default_commands or ["start", "help"])

    # default scope without language as a fallback
    fallback_cmds = build_bot_commands(
        base_names, lang=languages[0], translator=translator, key_prefix=key_prefix
    )
    if (
        await bot.set_my_commands(fallback_cmds, scope=BotCommandScopeDefault())
        is not True
    ):
        raise RuntimeError("Telegram did not apply the fallback menu")

    # language-specific sets for private chats (most common case)
    for lang in languages:
        cmds = build_bot_commands(
            base_names, lang=lang, translator=translator, key_prefix=key_prefix
        )
        if (
            await bot.set_my_commands(
                cmds, scope=BotCommandScopeAllPrivateChats(), language_code=lang
            )
            is not True
        ):
            raise RuntimeError("Telegram did not apply the language menu")

    # Menu button setup
    if menu_button == "commands":
        response = await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    else:
        response = await bot.set_chat_menu_button(menu_button=MenuButtonDefault())

    if response is not True:
        raise RuntimeError("Telegram did not apply the menu button")
