"""
Apply full configurations to Telegram bot.
"""

from collections.abc import Iterable

from aiogram import Bot
from aiogram.types import (
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
from .registry import CommandRegistry
from .translator import Translator


def _scope_obj(
    s: ScopeDef,
) -> (
    BotCommandScopeDefault
    | BotCommandScopeAllPrivateChats
    | BotCommandScopeAllGroupChats
    | BotCommandScopeAllChatAdministrators
    | BotCommandScopeChat
    | BotCommandScopeChatAdministrators
    | BotCommandScopeChatMember
):
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


async def apply_config(
    bot: Bot,
    cfg: CmdsConfig,
    *,
    translator: Translator | None = None,
) -> None:
    """
    Apply all configured scopes + menu button in order of specificity.
    """
    reg = CommandRegistry(cfg)
    scopes = _sorted_scopes(cfg.scopes)
    langs = cfg.languages or ["en"]

    for s in scopes:
        scope_obj = _scope_obj(s)
        target_langs = s.languages or langs
        names = list(reg.resolve_profile_commands(s.profile))
        for lang in target_langs:
            cmds = build_from_config(
                reg,
                names,
                lang=lang,
                translator=translator,
                key_prefix=cfg.i18n_key_prefix,
            )
            await bot.set_my_commands(cmds, scope=scope_obj, language_code=lang)

    # menu button (global default)
    if cfg.menu_button.mode == "commands":
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
