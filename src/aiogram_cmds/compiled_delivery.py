"""Python-owned Telegram boundary for explicitly compiled profile payloads."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommandScopeChat, BotCommandScopeChatMember

from .compiled import CompiledCommands, ProfileRequest, build_profile_batch
from .delivery import UNSET, CommandApplyResult, LanguageCode
from .engines import Engine, native_engine


async def apply_compiled_profile(
    bot: Bot,
    compiled: CompiledCommands,
    *,
    user_id: int,
    profile: str,
    chat_id: int | None = None,
    language: str = "en",
    language_code: str | None | LanguageCode = UNSET,
    previous_fingerprint: str | None = None,
    best_effort: bool = False,
    engine: Engine = "python",
) -> CommandApplyResult:
    native_engine(engine)
    if type(best_effort) is not bool:
        raise TypeError("best_effort must be a boolean")
    from .delivery import validate_fingerprint

    validate_fingerprint(previous_fingerprint)
    fingerprint = None
    try:
        scope = (
            BotCommandScopeChat(chat_id=user_id)
            if chat_id is None
            else BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
        )
        request = ProfileRequest(
            profile, language, bot.id, scope.model_dump_json(), language_code
        )
        payload = build_profile_batch(compiled, [request], engine=engine)[0]
        fingerprint = payload.fingerprint
        if previous_fingerprint == fingerprint:
            return CommandApplyResult("unchanged", fingerprint, fingerprint)
        commands = payload.bot_commands()
        if payload.language_code is None:
            response = await bot.set_my_commands(commands, scope=scope)
        else:
            response = await bot.set_my_commands(
                commands, scope=scope, language_code=payload.language_code
            )
        if response is not True:
            raise RuntimeError("Telegram did not apply the command menu")
    except Exception as error:
        if not best_effort:
            raise
        return CommandApplyResult("failed", fingerprint, error=error)
    return CommandApplyResult("applied", fingerprint, fingerprint)
