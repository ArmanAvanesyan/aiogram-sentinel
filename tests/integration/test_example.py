"""Exercise the runnable example through Telegram method models and Dispatcher."""

import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User

EXAMPLE = Path(__file__).parents[2] / "examples" / "minimal_bot.py"


def load_example(filename="minimal_bot.py"):
    spec = importlib.util.spec_from_file_location(
        "sentinel_example", EXAMPLE.with_name(filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_application_example_protects_child_and_explicitly_exempts_start():
    from aiogram.types import MessageEntity

    example = load_example("application_bot.py")
    dp = await example.create_dispatcher()
    bot = Bot("123456:TEST")
    bot.session.make_request = AsyncMock(return_value=update(100, "response").message)
    try:
        await dp.emit_startup()
        for number in range(1, 7):
            await dp.feed_update(bot, update(number, f"message {number}"))
        for number in (7, 8):
            event = update(number, "/start")
            event = event.model_copy(
                update={
                    "message": event.message.model_copy(
                        update={
                            "entities": [
                                MessageEntity(type="bot_command", offset=0, length=6)
                            ]
                        }
                    )
                }
            )
            await dp.feed_update(bot, event)
        texts = [call.args[1].text for call in bot.session.make_request.await_args_list]
        assert (
            texts
            == ["Accepted."] * 5
            + ["Welcome. Send text to exercise message protection."] * 2
        )
    finally:
        await bot.session.close()
        await dp.storage.close()


def update(number, text):
    return Update(
        update_id=number,
        message=Message(
            message_id=number,
            date=datetime.now(timezone.utc),
            chat=Chat(id=123, type="private"),
            from_user=User(id=123, is_bot=False, first_name="Test"),
            text=text,
        ),
    )


def test_import_has_no_logging_or_credential_side_effect(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    root = logging.getLogger()
    before = (root.level, tuple(root.handlers))
    load_example()
    assert (root.level, tuple(root.handlers)) == before


@pytest.mark.asyncio
async def test_example_router_applies_rate_limit_debounce_and_friendly_errors():
    example = load_example()
    dp = await example.build_dispatcher()
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    response = update(100, "response").message
    bot.session.make_request = AsyncMock(return_value=response)
    try:
        await dp.feed_update(bot, update(1, "/spam one"))
        await dp.feed_update(bot, update(2, "/spam two"))
        await dp.feed_update(bot, update(3, "/spam two"))
        methods = [call.args[1] for call in bot.session.make_request.await_args_list]
        assert len(methods) == 2
        assert all(isinstance(method, SendMessage) for method in methods)
        assert methods[0].text == "Message accepted."
        assert methods[1].text.startswith("Please wait ")
        assert all("show_alert" not in method.model_extra for method in methods)
    finally:
        await bot.session.close()
        await dp.storage.close()

    # A separate dispatcher has a fresh quota and proves error middleware runs.
    dp = await example.build_dispatcher()
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.session.make_request = AsyncMock(return_value=response)
    try:
        await dp.feed_update(bot, update(4, "/error"))
        method = bot.session.make_request.await_args.args[1]
        assert isinstance(method, SendMessage)
        assert method.text == "Please check your input and try again."
    finally:
        await bot.session.close()
        await dp.storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("setup_failure", [False, True])
async def test_example_main_propagates_failures_and_closes_resources(
    monkeypatch, setup_failure
):
    from types import SimpleNamespace

    example = load_example()
    monkeypatch.setenv("BOT_TOKEN", "example-only")
    monkeypatch.setattr(example.logging, "basicConfig", lambda **kwargs: None)
    for logger in (example.logger, logging.getLogger("aiogram_sentinel")):
        monkeypatch.setattr(logger, "level", logger.level)
    close_session = AsyncMock()
    bot = SimpleNamespace(session=SimpleNamespace(close=close_session))
    close_storage = AsyncMock()
    dp = SimpleNamespace(
        storage=SimpleNamespace(close=close_storage),
        start_polling=AsyncMock(side_effect=RuntimeError("polling failed")),
    )
    monkeypatch.setattr(example, "Bot", lambda token: bot)
    builder = AsyncMock(return_value=dp)
    if setup_failure:
        builder.side_effect = RuntimeError("setup failed")
    monkeypatch.setattr(example, "build_dispatcher", builder)
    with pytest.raises(RuntimeError, match="setup failed|polling failed"):
        await example.main()
    close_session.assert_awaited_once()
    if setup_failure:
        close_storage.assert_not_awaited()
    else:
        close_storage.assert_awaited_once()
