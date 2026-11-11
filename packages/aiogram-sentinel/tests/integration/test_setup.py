"""Exercise installed middleware through aiogram's real dispatcher."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Chat, Message, Update, User

from aiogram_sentinel import Sentinel, SentinelConfig
from aiogram_sentinel.exceptions import ConfigurationError
from aiogram_sentinel.middlewares.errors import ErrorConfig, ErrorHandlingMiddleware


@pytest.mark.asyncio
async def test_hooks_preserve_application_middlewares_and_handler_guard():
    dp = Dispatcher()
    router = Router()
    calls = []

    async def guard(handler, event, data):
        calls.append("guard")
        data["guarded"] = True
        return await handler(event, data)

    router.message.middleware(guard)

    @router.message()
    async def handler(message: Message, guarded: bool):
        assert guarded
        calls.append("handler")

    cfg = SentinelConfig(throttling_default_max=1)
    _, infra = await Sentinel.setup(dp, cfg, router, error_config=ErrorConfig())
    owned = tuple(router.message.middleware)
    assert any(isinstance(mw, ErrorHandlingMiddleware) for mw in owned)
    hook = AsyncMock()
    Sentinel.add_hooks(router, infra, cfg, on_rate_limited=hook)
    assert tuple(router.message.middleware) == owned
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    try:
        for number in (1, 2):
            await dp.feed_update(
                bot,
                Update(
                    update_id=number,
                    message=Message(
                        message_id=number,
                        date=datetime.now(timezone.utc),
                        chat=Chat(id=1, type="private"),
                        from_user=User(id=1, is_bot=False, first_name="Test"),
                        text=str(number),
                    ),
                ),
            )
        assert calls == ["guard", "handler", "guard"]
        hook.assert_awaited_once()
        Sentinel.add_hooks(router, infra, cfg)
        assert tuple(router.message.middleware) == owned
        with pytest.raises(ConfigurationError):
            await Sentinel.setup(dp, cfg, router)
        with pytest.raises(ConfigurationError):
            Sentinel.add_hooks(Router(), infra, cfg)
        with pytest.raises(ConfigurationError):
            Sentinel.add_hooks(router, infra, SentinelConfig())
    finally:
        await bot.session.close()
        await dp.storage.close()
