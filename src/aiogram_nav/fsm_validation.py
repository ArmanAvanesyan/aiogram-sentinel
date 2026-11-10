"""Public checks for lossless aiogram FSM identity mapping."""

from typing import cast

from aiogram import Dispatcher
from aiogram.fsm.storage.base import KeyBuilder, StorageKey

from .errors import ConfigurationError


def validate_fsm_storage(dispatcher: Dispatcher) -> tuple[str, ...] | None:
    # A correct StorageKey does not prove the store's builder preserves it.
    # Inspect known RedisStorage structurally so core never imports Redis.
    if not any(
        cls.__module__ == "aiogram.fsm.storage.redis" and cls.__name__ == "RedisStorage"
        for cls in type(dispatcher.storage).__mro__
    ):
        return None
    builder = getattr(dispatcher.storage, "key_builder", None)
    if not isinstance(builder, KeyBuilder):
        raise ConfigurationError("Redis FSM storage requires a verified key builder")
    identities = [
        StorageKey(bot_id=1, chat_id=7, user_id=11),
        StorageKey(bot_id=2, chat_id=7, user_id=11),
        StorageKey(bot_id=1, chat_id=8, user_id=11),
        StorageKey(bot_id=1, chat_id=7, user_id=12),
    ]
    try:
        keys = [builder.build(key, field) for key in identities for field in ("state", "data")]
        valid = (
            all(isinstance(cast(object, key), str) and key for key in keys) and len(set(keys)) == 8
        )
    except Exception as error:
        raise ConfigurationError("FSM key builder cannot encode navigation identities") from error
    if not valid:
        raise ConfigurationError(
            "FSM keys must separate bot/chat/user/field; use DefaultKeyBuilder(with_bot_id=True)"
        )

    return tuple(keys)
