"""
Apply full configurations to Telegram bot.
"""

import json
from collections.abc import Iterable
from typing import TypeAlias

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
    BotCommandScopeChatMember,
    BotCommandScopeDefault,
    MenuButtonCommands,
    MenuButtonDefault,
)

from .builders_configured import build_from_config
from .customize import CmdsConfig, ScopeDef
from .delivery import CommandBatchResult
from .registry import CommandRegistry
from .translator import Translator

ScopeObject: TypeAlias = (
    BotCommandScopeDefault
    | BotCommandScopeAllPrivateChats
    | BotCommandScopeAllGroupChats
    | BotCommandScopeAllChatAdministrators
    | BotCommandScopeChat
    | BotCommandScopeChatAdministrators
    | BotCommandScopeChatMember
)


def _scope_obj(s: ScopeDef) -> ScopeObject:
    if s.scope == "default":
        return BotCommandScopeDefault()
    if s.scope == "all_private_chats":
        return BotCommandScopeAllPrivateChats()
    if s.scope == "all_group_chats":
        return BotCommandScopeAllGroupChats()
    if s.scope == "all_chat_admins":
        return BotCommandScopeAllChatAdministrators()
    if s.scope in {"chat", "chat_admins", "chat_member"} and s.chat_id is None:
        raise ValueError("Chat command scopes require chat_id")
    if s.scope == "chat":
        assert s.chat_id is not None
        return BotCommandScopeChat(chat_id=s.chat_id)
    if s.scope == "chat_admins":
        assert s.chat_id is not None
        return BotCommandScopeChatAdministrators(chat_id=s.chat_id)
    if s.scope == "chat_member":
        if s.chat_id is None or s.user_id is None:
            raise ValueError("Chat-member command scopes require chat_id and user_id")
        return BotCommandScopeChatMember(chat_id=s.chat_id, user_id=s.user_id)
    raise ValueError(f"Unknown scope: {s.scope}")


def _sorted_scopes(scopes: Iterable[ScopeDef]) -> list[ScopeDef]:
    rank = {
        "chat_member": 0,
        "chat_admins": 1,
        "chat": 2,
        "all_chat_admins": 3,
        "all_group_chats": 4,
        "all_private_chats": 5,
        "default": 6,
    }
    return sorted(scopes, key=lambda s: rank[s.scope])


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
) -> CommandBatchResult:
    """Apply prepared targets with optional partial-completion evidence."""
    if type(best_effort) is not bool:
        raise TypeError("best_effort must be a boolean")
    completed: list[str] = []
    target = "configuration"
    try:
        # Validate/render all scopes before performing the first network effect.
        for scope, slot, commands in _targets(cfg, translator):
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
