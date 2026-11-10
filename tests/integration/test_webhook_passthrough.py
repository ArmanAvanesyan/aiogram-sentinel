"""Propagated infrastructure failures remain visible to the webhook transport."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from aiogram_sentinel import ErrorConfig, InfraBundle, Sentinel, SentinelConfig
from aiogram_sentinel.exceptions import BackendOperationError

PAYLOAD = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 42, "is_bot": False, "first_name": "Example"},
        "text": "example",
    },
}


@pytest.mark.parametrize("origin", ["handler", "backend"])
@pytest.mark.parametrize("failure", ["redis", "timeout"])
async def test_foreground_webhook_and_dispatcher_errors_preserve_503(origin, failure):
    if failure == "redis":
        RedisError = pytest.importorskip("redis.exceptions").RedisError
        error = RedisError("unavailable")
    else:
        error = TimeoutError("timeout")
    dp, router = Dispatcher(), Router()
    friendly = AsyncMock()

    @router.message()
    async def business(message):
        if origin == "backend":
            raise AssertionError("The unavailable spam backend must stop dispatch")
        raise error

    @dp.errors()
    async def dispatcher_error(event):
        if origin == "backend" and failure == "redis":
            assert isinstance(event.exception, BackendOperationError)
            assert event.exception.__cause__ is error
        else:
            assert event.exception is error
        raise event.exception

    infra = None
    if origin == "backend":
        pytest.importorskip("redis")
        from aiogram_sentinel.storage import MemoryDebounce, RedisRateLimiter

        client = AsyncMock()
        client.eval.side_effect = error
        infra = InfraBundle(RedisRateLimiter(client, "webhook-test"), MemoryDebounce())

    await Sentinel.setup(
        dp,
        SentinelConfig(),
        router,
        infra=infra,
        error_config=ErrorConfig(
            reraise_exceptions=(type(error), BackendOperationError),
            send_strategy=friendly,
        ),
    )
    bot = Bot("123456:TEST")

    @web.middleware
    async def infrastructure_status(request, handler):
        try:
            return await handler(request)
        except (type(error), BackendOperationError):
            return web.Response(status=503)

    app = web.Application(middlewares=[infrastructure_status])
    SimpleRequestHandler(dp, bot, handle_in_background=False).register(
        app, path="/webhook"
    )
    client = TestClient(TestServer(app))
    try:
        await client.start_server()
        response = await client.post("/webhook", json=PAYLOAD)
        assert response.status == 503
        friendly.assert_not_awaited()
    finally:
        await client.close()
        await bot.session.close()
        await dp.storage.close()


async def test_passthrough_never_swallows_task_cancellation():
    from aiogram_sentinel import ErrorHandlingMiddleware, KeyBuilder

    handler = AsyncMock(side_effect=asyncio.CancelledError)
    middleware = ErrorHandlingMiddleware(ErrorConfig(), KeyBuilder("test"))
    with pytest.raises(asyncio.CancelledError):
        await middleware(handler, Message.model_validate(PAYLOAD["message"]), {})
