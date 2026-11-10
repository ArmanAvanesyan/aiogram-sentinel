"""Regression cases found during the pre-Redis concurrency audit."""

from __future__ import annotations

import asyncio

import pytest
from aiogram import Bot, Dispatcher

from aiogram_idle import ConfigurationError, ControlContext, IdleRuntime
from aiogram_idle.presentation import TelegramPromptPresenter
from tests.runtime_helpers import make_harness
from tests.test_telegram import FakeRuntime


async def test_runtimes_sharing_backend_share_conversation_coordination():
    h = await make_harness()
    other = IdleRuntime(
        backend=h.backend,
        policies=h.runtime.policies,
        adapters={"form": h.adapter},
        presenter=h.presenter,
        namespace="test",
    )
    started = asyncio.Event()

    async def mutate():
        started.set()
        return await other.for_conversation(h.key).touch(
            expected=h.activity.guard, operation_id="other-touch"
        )

    task = None
    try:
        async with h.runtime.coordinator.hold(h.key):
            task = asyncio.create_task(mutate())
            await started.wait()
            await asyncio.sleep(0)
            assert not task.done(), "a second runtime bypassed the conversation lock"
    finally:
        if task is not None:
            await task


async def test_continue_does_not_extend_an_already_elapsed_grace_window():
    h = await make_harness()
    await h.due()
    prompt = await h.runtime.current_prompt(h.key)
    assert prompt is not None
    context = ControlContext(
        h.key, h.key.user_id, prompt_id=prompt.prompt_id, operation_id="late-answer"
    )
    h.clock.advance(21)
    result = await h.runtime.continue_current(context)
    assert not result.accepted, "a delayed poller must not grant additional grace"
    assert "resume" not in h.adapter.calls


async def test_dispatcher_rejects_presenter_for_different_bot_before_binding():
    from aiogram_idle.integration import install

    bot_a, bot_b = Bot("123456:ABC"), Bot("654321:ABC")
    runtime = FakeRuntime(bot_a)
    runtime.bot = None
    runtime.presenter = TelegramPromptPresenter(bot_a)
    dispatcher = Dispatcher()
    install(runtime, dispatcher)
    try:
        with pytest.raises(ConfigurationError):
            await dispatcher.emit_startup(bot=bot_b)
        assert runtime.bot is None
    finally:
        await dispatcher.fsm.close()
        await bot_a.session.close()
        await bot_b.session.close()


async def test_disabled_fsm_does_not_borrow_unheld_shared_aiogram_lock():
    from aiogram.fsm.storage.memory import SimpleEventIsolation
    from aiogram.types import Update

    from aiogram_idle.coordinator import AiogramMemoryCoordinator
    from aiogram_idle.integration import install
    from tests.test_telegram import KEY, message

    bot = Bot("123456:ABC")
    dispatcher = Dispatcher()
    runtime = FakeRuntime(bot)
    isolation = SimpleEventIsolation()
    runtime.coordinator = AiogramMemoryCoordinator(isolation)
    install(runtime, dispatcher, lifecycle=False)
    called = asyncio.Event()

    @dispatcher.message()
    async def handler(message):
        called.set()

    task = None
    try:
        async with runtime.coordinator.hold(KEY):
            task = asyncio.create_task(
                dispatcher.feed_update(bot, Update(update_id=1, message=message()))
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not called.is_set(), "disabled FSM borrowed a lock it never held"
        await task
        assert called.is_set()
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_same_fsm_isolation_reuses_coordinator_and_conflicting_one_rejected():
    from aiogram.fsm.storage.memory import SimpleEventIsolation

    from aiogram_idle.coordinator import AiogramMemoryCoordinator
    from aiogram_idle.integration import install

    bot = Bot("123456:ABC")
    runtime = FakeRuntime(bot)
    isolation = SimpleEventIsolation()
    coordinator = AiogramMemoryCoordinator(isolation)
    runtime.coordinator = coordinator
    first = Dispatcher(events_isolation=isolation)
    second = Dispatcher(events_isolation=SimpleEventIsolation())
    try:
        install(runtime, first, lifecycle=False)
        assert runtime.coordinator is coordinator
        with pytest.raises(ConfigurationError):
            install(runtime, second, lifecycle=False)
        assert not second.get("_aiogram_idle_installed")
    finally:
        await first.fsm.close()
        await second.fsm.close()
        await bot.session.close()


async def test_coordinator_scope_capability_expires_and_is_task_scoped():
    from aiogram_idle.coordinator import MemoryCoordinator

    coordinator = MemoryCoordinator()
    key = "conversation"
    assert coordinator.scope_token(key) is None
    assert coordinator.active_scopes == 0
    async with coordinator.hold(key):
        capability = coordinator.scope_token(key)
        assert capability is not None and coordinator.scope_active(capability)
        assert coordinator.active_scopes == 1
        async with coordinator.hold(key):
            assert coordinator.scope_token(key) is capability
            assert coordinator.active_scopes == 1

        async def child():
            assert coordinator.scope_token(key) is None
            assert not coordinator.owns(key)
            # A captured token can be checked for liveness; it grants no lock.
            assert coordinator.scope_active(capability)

        await asyncio.create_task(child())
    assert not coordinator.scope_active(capability)
    assert coordinator.active_scopes == 0


async def test_borrowed_aiogram_scope_reuses_live_capability_and_expires():
    from aiogram.fsm.storage.memory import SimpleEventIsolation

    from aiogram_idle.coordinator import AiogramMemoryCoordinator
    from tests.test_telegram import KEY

    coordinator = AiogramMemoryCoordinator(SimpleEventIsolation())
    async with coordinator.borrowed(KEY):
        capability = coordinator.scope_token(KEY)
        assert coordinator.active_scopes == 1
        async with coordinator.hold(KEY):
            assert coordinator.scope_token(KEY) is capability
        async with coordinator.borrowed(KEY):
            assert coordinator.scope_token(KEY) is capability
        assert coordinator.active_scopes == 1
    assert not coordinator.scope_active(capability)
    assert coordinator.active_scopes == 0


async def test_copied_context_cannot_restore_expired_same_task_ownership():
    from contextvars import copy_context

    from aiogram_idle.coordinator import MemoryCoordinator

    coordinator = MemoryCoordinator()
    async with coordinator.hold("key"):
        captured = copy_context()
        assert captured.run(coordinator.owns, "key")
    assert not captured.run(coordinator.owns, "key")
    assert captured.run(coordinator.scope_token, "key") is None


async def test_coordinator_counts_and_cleans_cancelled_waiters():
    from aiogram_idle.coordinator import MemoryCoordinator

    coordinator = MemoryCoordinator()

    async def waiter():
        async with coordinator.hold("key"):
            pass

    async with coordinator.hold("key"):
        task = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        assert coordinator.active_scopes == 2
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert coordinator.active_scopes == 1
    assert coordinator.active_scopes == 0
    assert coordinator.lock_count == 0


async def test_pending_operation_does_not_admit_business_handler(monkeypatch):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from aiogram.exceptions import TelegramRetryAfter
    from aiogram.methods import SendMessage
    from aiogram.types import Chat, Message, Update, User

    h = await make_harness()
    await h.due()
    h.adapter.resume_error = TelegramRetryAfter(
        method=SendMessage(chat_id=2, text="resume"), message="retry", retry_after=5
    )
    assert (await h.answer()).outcome == "resuming"
    bot = Bot("1:ABC")
    bot.send_message = AsyncMock()
    dispatcher = Dispatcher()
    h.runtime.install(dispatcher, lifecycle=False)
    business = []

    @dispatcher.message()
    async def handler(message):
        business.append(message.text)

    event = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=2, type="private"),
        from_user=User(id=2, is_bot=False, first_name="User"),
        text="new draft text",
    )
    await dispatcher.feed_update(bot, Update(update_id=8, message=event))
    assert business == []
    assert bot.send_message.await_count == 1
    assert await h.runtime.is_busy(h.key)
    h.adapter.resume_error = None
    await h.due(5)
    await dispatcher.feed_update(bot, Update(update_id=9, message=event))
    assert business == ["new draft text"]
    await dispatcher.fsm.close()
    await bot.session.close()
