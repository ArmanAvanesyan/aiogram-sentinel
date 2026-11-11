from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    ReplyKeyboardMarkup,
    Update,
    User,
)

from aiogram_idle.controls import (
    CommandPromptControls,
    ControlContext,
    ControlResult,
    InlinePromptControls,
    ReplyPromptControls,
    handle_control,
)
from aiogram_idle.coordinator import AiogramMemoryCoordinator, MemoryCoordinator
from aiogram_idle.errors import ConfigurationError, UnsupportedContext
from aiogram_idle.integration import install, private_identity
from aiogram_idle.models import IdleConversationKey, MessageRef
from aiogram_idle.presentation import (
    FinishRequest,
    PromptReceipt,
    PromptRequest,
    PromptTexts,
    QuietHours,
    TelegramPromptPresenter,
    callback_data,
)

NOW = datetime(2026, 1, 1, 22, tzinfo=timezone.utc)
KEY = IdleConversationKey("default", 123456, 42, 42)


def message(text: str = "hello", message_id: int = 1) -> Message:
    return Message(
        message_id=message_id,
        date=NOW,
        chat=Chat(id=42, type="private"),
        from_user=User(id=42, is_bot=False, first_name="User"),
        text=text,
    )


@pytest.fixture
def bot() -> Bot:
    value = Bot("123456:ABC")
    value.send_message = AsyncMock(return_value=message(message_id=99))
    value.edit_message_text = AsyncMock(return_value=message(message_id=99))
    value.edit_message_reply_markup = AsyncMock(return_value=message(message_id=99))
    value.answer_callback_query = AsyncMock(return_value=True)
    return value


@pytest.mark.parametrize("style", ["reply", "inline", "commands", "hybrid"])
async def test_presenter_question_delivery_and_outcome(bot: Bot, style: str) -> None:
    presenter = TelegramPromptPresenter(bot)
    receipt = await presenter.show(
        PromptRequest(
            KEY,
            "p1",
            "continue-token",
            "cancel-token",
            controls=style,
            now=NOW.timestamp(),
        )
    )
    assert receipt.messages == (MessageRef(42, 99),)
    assert receipt.shown_at == NOW.timestamp()
    kwargs = bot.send_message.call_args.kwargs
    if style == "reply":
        assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)
    elif style in {"inline", "hybrid"}:
        assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "idle:c:continue-token"
    else:
        assert kwargs["reply_markup"] is None
        assert "/continue" in bot.send_message.call_args.args[1]
    assert bot.edit_message_text.await_count == 0
    await presenter.finish(FinishRequest(receipt, "timed_out"))
    assert bot.edit_message_text.call_args.args[0] == "Cancelled due to inactivity."
    await presenter.strip(receipt)
    assert bot.edit_message_reply_markup.await_count == int(style in {"inline", "hybrid"})


async def test_hybrid_uses_two_messages_and_quiet_hours(bot: Bot) -> None:
    presenter = TelegramPromptPresenter(
        bot,
        quiet_hours=QuietHours("UTC", time(22), time(8)),
    )
    tray = ReplyKeyboardMarkup(keyboard=[])
    receipt = await presenter.show(
        PromptRequest(
            KEY,
            "p1",
            "ct",
            "xt",
            controls="hybrid",
            reply_keyboard=tray,
            now=NOW.timestamp(),
        )
    )
    assert len(receipt.messages) == 2
    assert bot.send_message.await_count == 2
    assert all(call.kwargs["disable_notification"] for call in bot.send_message.call_args_list)
    assert bot.send_message.call_args_list[1].kwargs["reply_markup"] is tray


async def test_quiet_interval_validation_and_daytime() -> None:
    quiet = QuietHours("UTC", time(8), time(17))
    assert not await quiet(KEY, NOW.timestamp())
    assert await quiet(KEY, NOW.replace(hour=10).timestamp())
    with pytest.raises(ValueError):
        QuietHours("UTC", time(8), time(8))
    with pytest.raises(ValueError):
        QuietHours("UTC", time(8, tzinfo=timezone.utc), time(9))
    with pytest.raises(ValueError):
        PromptTexts(continue_label="same", cancel_label="same")
    with pytest.raises(ValueError):
        callback_data("c", "")
    with pytest.raises(ValueError):
        callback_data("c", "é" * 40)
    assert InlinePromptControls().match("unknown") is None
    assert ReplyPromptControls().match("ordinary text") is None


async def test_presenter_invalid_mode_missing_bot_and_missing_receipt(bot: Bot) -> None:
    presenter = TelegramPromptPresenter()
    with pytest.raises(ValueError):
        await presenter.show(PromptRequest(KEY, "p"))
    with pytest.raises(ValueError):
        await TelegramPromptPresenter(bot).show(PromptRequest(KEY, "p", controls="bad"))
    assert (await presenter.finish(FinishRequest(PromptReceipt("p"), "cancelled"))).unavailable


async def test_coordinator_child_cannot_borrow_and_releases_cancelled_waiter() -> None:
    coordinator = MemoryCoordinator()
    entered = asyncio.Event()

    async def child() -> None:
        assert not coordinator.owns(KEY)
        async with coordinator.hold(KEY):
            entered.set()

    async with coordinator.hold(KEY):
        assert coordinator.owns(KEY)
        async with coordinator.hold(KEY):
            assert coordinator.lock_count == 1
        task = asyncio.create_task(child())
        await asyncio.sleep(0)
        assert not entered.is_set()
        cancelled = asyncio.create_task(child())
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
    await task
    assert entered.is_set()
    assert coordinator.lock_count == 0


class FakeRuntime:
    def __init__(self, bot: Bot) -> None:
        self.namespace = "default"
        self.coordinator = MemoryCoordinator()
        self.presenter = TelegramPromptPresenter(bot)
        self.bot: Bot | None = None
        self.prompt: PromptReceipt | None = None
        self.calls: list[tuple[str, ControlContext]] = []
        self.marker = object()
        self.started = False

    def for_conversation(self, key: IdleConversationKey) -> object:
        assert self.coordinator.owns(key)
        return self.marker

    async def current_prompt(self, key: IdleConversationKey) -> PromptReceipt | None:
        return self.prompt

    async def continue_current(self, context: ControlContext) -> ControlResult:
        self.calls.append(("continue", context))
        return ControlResult(self.prompt is not None, "continued")

    async def cancel_current(self, context: ControlContext) -> ControlResult:
        self.calls.append(("cancel", context))
        return ControlResult(self.prompt is not None, "cancelled")

    async def is_busy(self, key):
        return False

    async def inspect(self, key):
        return None

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False


@pytest.mark.parametrize("fsm", ["off", "on", "middleware-disabled"])
async def test_real_dispatcher_injection_and_whole_handler_isolation(bot: Bot, fsm: str) -> None:
    dp = Dispatcher(
        events_isolation=SimpleEventIsolation() if fsm != "off" else None,
        disable_fsm=fsm == "middleware-disabled",
    )
    runtime = FakeRuntime(bot)
    install(runtime, dp, lifecycle=False)
    if fsm != "off":
        assert isinstance(runtime.coordinator, AiogramMemoryCoordinator)
    entered = asyncio.Event()
    release = asyncio.Event()
    worker_entered = asyncio.Event()
    router = Router()

    @router.message()
    async def handler(incoming: Message, idle_context: object) -> None:
        assert idle_context is runtime.marker
        entered.set()
        await release.wait()

    dp.include_router(router)
    task = asyncio.create_task(dp.feed_update(bot, Update(update_id=1, message=message())))
    await entered.wait()

    async def worker() -> None:
        async with runtime.coordinator.hold(KEY):
            worker_entered.set()

    work = asyncio.create_task(worker())
    await asyncio.sleep(0)
    assert not worker_entered.is_set()
    release.set()
    await task
    await work
    assert worker_entered.is_set()
    with pytest.raises(ConfigurationError):
        install(runtime, dp)
    await dp.fsm.close()


async def test_dispatcher_controls_precede_business_and_cancel_falls_through(bot: Bot) -> None:
    dp = Dispatcher()
    runtime = FakeRuntime(bot)
    install(runtime, dp, lifecycle=False)
    business: list[str] = []

    @dp.message()
    async def handler(incoming: Message) -> None:
        business.append(incoming.text or "")

    await dp.feed_update(bot, Update(update_id=1, message=message("/cancel")))
    assert business == ["/cancel"]
    await dp.feed_update(bot, Update(update_id=2, message=message("/continue")))
    assert business == ["/cancel"]
    runtime.prompt = PromptReceipt("p", controls="reply")
    await dp.feed_update(bot, Update(update_id=3, message=message("Continue")))
    assert runtime.calls[-1][0] == "continue"
    await dp.feed_update(bot, Update(update_id=4, message=message("draft text")))
    assert business[-1] == "draft text"
    await dp.fsm.close()


async def test_stale_and_valid_inline_acknowledged(bot: Bot) -> None:
    runtime = FakeRuntime(bot)
    query = CallbackQuery(
        id="q",
        from_user=message().from_user,
        chat_instance="ci",
        message=message(),
        data="idle:c:token",
    ).as_(bot)
    assert await handle_control(runtime, query, KEY, bot=bot, texts=PromptTexts(), update_id=1)
    assert bot.answer_callback_query.await_count == 1
    assert runtime.calls[-1][1].token == "token"
    assert not await handle_control(
        runtime,
        query.model_copy(update={"data": "other:callback"}),
        KEY,
        bot=bot,
        texts=PromptTexts(),
        update_id=2,
    )
    await handle_control(
        runtime,
        query.model_copy(update={"data": "idle:invalid"}),
        KEY,
        bot=bot,
        texts=PromptTexts(),
        update_id=3,
    )
    assert bot.answer_callback_query.await_count == 2


async def test_identity_rejects_group_and_wrong_actor(bot: Bot) -> None:
    assert private_identity(Update(update_id=1, message=message()), bot, "default") == KEY
    group = message().model_copy(update={"chat": Chat(id=-42, type="group")})
    with pytest.raises(UnsupportedContext):
        private_identity(Update(update_id=2, message=group), bot, "default")
    wrong = message().model_copy(update={"from_user": User(id=43, is_bot=False, first_name="x")})
    with pytest.raises(UnsupportedContext):
        private_identity(Update(update_id=3, message=wrong), bot, "default")
    assert await CommandPromptControls().match(message("hello"), bot) is None
