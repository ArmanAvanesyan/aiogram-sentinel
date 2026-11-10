"""SDK command scope creation and stable target precedence."""

from collections.abc import Iterable
from typing import TypeAlias

from aiogram.types import (
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
    BotCommandScopeChatMember,
    BotCommandScopeDefault,
)

from .customize import ScopeDef

ScopeObject: TypeAlias = (
    BotCommandScopeDefault
    | BotCommandScopeAllPrivateChats
    | BotCommandScopeAllGroupChats
    | BotCommandScopeAllChatAdministrators
    | BotCommandScopeChat
    | BotCommandScopeChatAdministrators
    | BotCommandScopeChatMember
)


def scope_object(s: ScopeDef) -> ScopeObject:
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


def sorted_scopes(scopes: Iterable[ScopeDef]) -> list[ScopeDef]:
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
