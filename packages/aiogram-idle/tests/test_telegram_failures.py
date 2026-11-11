from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, time, timezone
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.fsm.storage.base import BaseEventIsolation
from aiogram.fsm.strategy import FSMStrategy
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from aiogram.methods.base import TelegramMethod, TelegramType
from aiogram.types import CallbackQuery, Message, Update, User

from aiogram_idle.controls import InlinePromptControls, handle_control
from aiogram_idle.coordinator import AiogramMemoryCoordinator
from aiogram_idle.errors import ConfigurationError
from aiogram_idle.integration import IdleContextMiddleware, install
from aiogram_idle.models import MessageRef
from aiogram_idle.presentation import (
    FinishRequest,
    PromptReceipt,
    PromptRequest,
    PromptTexts,
    QuietHours,
    TelegramPromptPresenter,
)
from tests.test_telegram import KEY, FakeRuntime, message


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.methods: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        self.methods.append(method)
        if isinstance(method, GetMe):
            return User(id=bot.id, is_bot=True, first_name="Test", username="TestBot")
        if isinstance(method, AnswerCallbackQuery):
            return True
        return message(message_id=99)

    async def stream_content(self, url: str, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""


async def test_real_telegram_method_objects_and_command_mentions() -> None:
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    presenter = TelegramPromptPresenter(bot)
    receipt = await presenter.show(PromptRequest(KEY, "p", controls="commands"))
    assert isinstance(session.methods[0], SendMessage)
    assert session.methods[0].reply_markup is None
    runtime = FakeRuntime(bot)
    runtime.prompt = receipt
    assert await handle_control(
        runtime,
        message("/continue@TestBot"),
        KEY,
        bot=bot,
        texts=PromptTexts(),
        update_id=1,
    )
    assert runtime.calls[-1][0] == "continue"
    assert not await handle_control(
        runtime,
        message("/continue@OtherBot"),
        KEY,
        bot=bot,
        texts=PromptTexts(),
        update_id=2,
    )
    await bot.session.close()


async def test_presenter_missing_message_cleanup_and_retry_after() -> None:
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    presenter = TelegramPromptPresenter(bot)
    receipt = PromptReceipt("p", (MessageRef(42, 99),))

    async def missing(*args: Any, **kwargs: Any) -> Message:
        raise TelegramBadRequest(
            method=SendMessage(chat_id=42, text="x"), message="message to edit not found"
        )

    bot.edit_message_text = missing
    bot.edit_message_reply_markup = missing
    assert (await presenter.finish(FinishRequest(receipt, "continued"))).unavailable
    assert (await presenter.strip(receipt)).unavailable

    async def limited(*args: Any, **kwargs: Any) -> Message:
        raise TelegramRetryAfter(
            method=SendMessage(chat_id=42, text="x"), message="wait", retry_after=5
        )

    bot.send_message = limited
    with pytest.raises(TelegramRetryAfter):
        await presenter.show(PromptRequest(KEY, "p", controls="commands"))
    await bot.session.close()


async def test_stale_cleanup_and_acknowledgement_error_do_not_undo_result() -> None:
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    runtime = FakeRuntime(bot)
    query = CallbackQuery(
        id="q",
        from_user=message().from_user,
        chat_instance="ci",
        message=message().model_copy(
            update={
                "from_user": User(id=bot.id, is_bot=True, first_name="Bot"),
            }
        ),
        data="idle:c:old-token",
    )
    assert await handle_control(runtime, query, KEY, bot=bot, texts=PromptTexts(), update_id=1)
    assert len(session.methods) == 1
    assert isinstance(session.methods[0], AnswerCallbackQuery)

    async def expired(*args: Any, **kwargs: Any) -> bool:
        raise TelegramBadRequest(
            method=AnswerCallbackQuery(callback_query_id="q"), message="query is too old"
        )

    bot.answer_callback_query = expired
    assert await handle_control(runtime, query, KEY, bot=bot, texts=PromptTexts(), update_id=2)
    assert InlinePromptControls().match("idle:y:token") is None
    await bot.session.close()


async def test_exception_still_acknowledges_callback() -> None:
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    runtime = FakeRuntime(bot)

    async def broken(context: object) -> object:
        raise RuntimeError("unavailable")

    runtime.continue_current = broken
    query = CallbackQuery(
        id="q",
        from_user=message().from_user,
        chat_instance="ci",
        message=message(),
        data="idle:c:token",
    )
    with pytest.raises(RuntimeError):
        await handle_control(runtime, query, KEY, bot=bot, texts=PromptTexts(), update_id=1)
    assert isinstance(session.methods[-1], AnswerCallbackQuery)
    await bot.session.close()


async def test_lifecycle_and_unsupported_configuration() -> None:
    bot = Bot("123456:ABC", session=RecordingSession())
    runtime = FakeRuntime(bot)
    dp = Dispatcher()
    install(runtime, dp)
    await dp.emit_startup(bot=bot)
    assert runtime.started
    await dp.emit_shutdown()
    assert not runtime.started
    with pytest.raises(ConfigurationError):
        install(FakeRuntime(bot), Dispatcher(fsm_strategy=FSMStrategy.CHAT))
    with pytest.raises(ValueError):
        AiogramMemoryCoordinator(object())

    class UnsupportedIsolation(BaseEventIsolation):
        @asynccontextmanager
        async def lock(self, key: object) -> AsyncGenerator[None, None]:
            yield

        async def close(self) -> None:
            return None

    with pytest.raises(ConfigurationError):
        install(FakeRuntime(bot), Dispatcher(events_isolation=UnsupportedIsolation()))
    await bot.session.close()


async def test_middleware_requires_bot_and_rejects_cross_bot_binding() -> None:
    bot = Bot("123456:ABC", session=RecordingSession())
    runtime = FakeRuntime(bot)
    middleware = IdleContextMiddleware(runtime)

    async def handler(event: object, data: dict[str, Any]) -> str:
        return "handled"

    assert await middleware(handler, message(), {}) == "handled"
    with pytest.raises(ConfigurationError):
        await middleware(handler, Update(update_id=1, message=message()), {})
    runtime.bot = Bot("654321:ABC", session=RecordingSession())
    with pytest.raises(ConfigurationError):
        await middleware(handler, Update(update_id=1, message=message()), {"bot": bot})
    await runtime.bot.session.close()
    await bot.session.close()


async def test_quiet_hours_repeated_dst_hour_and_invalid_labels() -> None:
    quiet = QuietHours("America/New_York", time(1), time(2))
    first = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).timestamp()
    second = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).timestamp()
    assert await quiet(KEY, first)
    assert await quiet(KEY, second)
    with pytest.raises(ValueError):
        PromptTexts(continue_label="")


async def test_hybrid_retry_reuses_confirmed_question_stage() -> None:
    from unittest.mock import AsyncMock

    from aiogram.types import ReplyKeyboardMarkup

    from aiogram_idle.effects import OperationEffects
    from aiogram_idle.models import IdleSnapshot, PendingOperation, Phase
    from tests.runtime_helpers import make_harness

    harness = await make_harness()
    runtime, clock, key = harness.runtime, harness.clock, harness.key
    before = await runtime.backend.load(key)
    assert before is not None
    from dataclasses import replace

    await runtime.backend.transition(
        key,
        expected_version=before.store_version,
        operation_id="prepare-hybrid",
        fingerprint="prepare-hybrid",
        transform=lambda old: replace(
            old,
            idle=IdleSnapshot(
                phase=Phase.PROMPT_PENDING,
                operation=PendingOperation(
                    operation_id="hybrid-op",
                    kind="prompt",
                    started_at=clock.now(),
                ),
            ),
        ),
    )
    session_transport = RecordingSession()
    bot = Bot(f"{key.bot_id}:ABC", session=session_transport)
    limited = TelegramRetryAfter(
        method=SendMessage(chat_id=42, text="tray"),
        message="wait",
        retry_after=5,
    )
    bot.send_message = AsyncMock(
        side_effect=[message(message_id=98), limited, message(message_id=99)]
    )
    async with runtime.coordinator.hold(key):
        effects = OperationEffects(runtime, key, "hybrid-op", None)
        request = PromptRequest(
            key,
            "p",
            "ct",
            "xt",
            controls="hybrid",
            now=clock.now(),
            effects=effects,
            reply_keyboard=ReplyKeyboardMarkup(keyboard=[]),
        )
        telegram = TelegramPromptPresenter(bot)
        with pytest.raises(TelegramRetryAfter):
            await telegram.show(request)
        receipt = await telegram.show(request)
        assert receipt.messages == (MessageRef(42, 98), MessageRef(42, 99))
        assert bot.send_message.await_count == 3
        assert bot.send_message.call_args_list[0].args[1] == "Do you want to continue?"
        assert bot.send_message.call_args_list[2].args[1] == "Choose an action."
    await bot.session.close()


async def test_locale_resolver_pins_reply_labels_for_current_prompt() -> None:
    bot = Bot("123456:ABC", session=RecordingSession())

    async def locale(key: object) -> str:
        return "hy"

    presenter = TelegramPromptPresenter(
        bot,
        locale_resolver=locale,
        texts=lambda language: PromptTexts(
            continue_label=f"continue-{language}", cancel_label=f"cancel-{language}"
        ),
    )
    receipt = await presenter.show(PromptRequest(KEY, "p", controls="reply"))
    assert receipt.locale == "hy"
    runtime = FakeRuntime(bot)
    runtime.prompt = receipt
    assert await handle_control(
        runtime,
        message("continue-hy"),
        KEY,
        bot=bot,
        texts=presenter.texts(receipt.locale),
        update_id=10,
    )
    assert runtime.calls[-1][0] == "continue"
    await bot.session.close()


async def test_callback_acknowledged_before_slow_adapter():
    import asyncio

    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    runtime = FakeRuntime(bot)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow(context):
        entered.set()
        await release.wait()
        return ControlResult(True, "continued")

    from aiogram_idle.controls import ControlResult

    runtime.continue_current = slow
    query = CallbackQuery(
        id="slow",
        from_user=message().from_user,
        chat_instance="ci",
        message=message(),
        data="idle:c:token",
    )
    task = asyncio.create_task(
        handle_control(runtime, query, KEY, bot=bot, texts=PromptTexts(), update_id=7)
    )
    await asyncio.wait_for(entered.wait(), 2)
    assert isinstance(session.methods[0], AnswerCallbackQuery)
    release.set()
    await task
    await bot.session.close()
