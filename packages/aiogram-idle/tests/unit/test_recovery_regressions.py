from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage

from aiogram_idle import Phase
from aiogram_idle.effects import OperationEffects
from tests.runtime_helpers import make_harness


async def test_repeated_prompt_cycles_have_fresh_ids_and_bounded_controls():
    h = await make_harness()
    prompt_ids = set()
    for cycle in range(10):
        await h.due()
        prompt = await h.runtime.current_prompt(h.key)
        assert prompt is not None
        assert prompt.prompt_id not in prompt_ids
        prompt_ids.add(prompt.prompt_id)
        assert (await h.answer(operation_id=f"continue:{cycle}")).outcome == "continued"
    assert len(h.presenter.questions) == 10


async def test_question_receipt_saved_before_cancellation_recovers_without_resending(monkeypatch):
    h = await make_harness()
    checkpoint = OperationEffects.checkpoint
    show = h.presenter.show

    async def slow_delivery(request):
        h.clock.advance(1)
        return await show(request)

    async def interrupt(self, stage, state, result=None):
        if stage == "question" and state == "confirmed":
            raise asyncio.CancelledError
        await checkpoint(self, stage, state, result)

    monkeypatch.setattr(h.presenter, "show", slow_delivery)
    monkeypatch.setattr(OperationEffects, "checkpoint", interrupt)
    with pytest.raises(asyncio.CancelledError):
        await h.due()
    record = await h.runtime.inspect(h.key)
    assert record.idle.prompt.messages
    monkeypatch.setattr(OperationEffects, "checkpoint", checkpoint)
    await h.runtime.run_once()
    record = await h.runtime.inspect(h.key)
    assert record.idle.phase is Phase.PROMPTED
    assert record.idle.deadline == 1031
    assert len(h.presenter.questions) == 1


async def test_partial_control_registration_recovers_before_delivery(monkeypatch):
    h = await make_harness()
    reserve = h.backend.reserve_control
    count = 0

    async def interrupt(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise asyncio.CancelledError
        return await reserve(*args, **kwargs)

    monkeypatch.setattr(h.backend, "reserve_control", interrupt)
    with pytest.raises(asyncio.CancelledError):
        await h.due()
    monkeypatch.setattr(h.backend, "reserve_control", reserve)
    await h.runtime.run_once()
    prompt = await h.runtime.current_prompt(h.key)
    assert prompt is not None
    assert await h.backend.resolve_control(h.key, prompt.continue_token)
    assert await h.backend.resolve_control(h.key, prompt.cancel_token)
    assert len(h.presenter.questions) == 1


async def test_control_retry_reports_pending_then_completes():
    h = await make_harness()
    await h.due()
    h.adapter.resume_error = TelegramRetryAfter(
        method=SendMessage(chat_id=2, text="resume"),
        message="retry",
        retry_after=3,
    )
    answer = await h.answer()
    assert answer.accepted and answer.outcome == "resuming"
    h.adapter.resume_error = None
    await h.due(3)
    assert await h.phase() is Phase.ACTIVE
    assert len(h.presenter.questions) == 1


async def test_runtime_locale_is_frozen_in_prompt():
    h = await make_harness()

    async def locale(key):
        return "hy"

    h.runtime.locale_resolver = locale
    await h.due()
    prompt = await h.runtime.current_prompt(h.key)
    assert prompt.locale == "hy"
    assert h.presenter.questions[0].locale == "hy"


async def test_wrong_presenter_receipt_never_becomes_active_prompt(monkeypatch):
    h = await make_harness()
    show = h.presenter.show

    async def wrong_identity(request):
        return replace(await show(request), prompt_id="different")

    monkeypatch.setattr(h.presenter, "show", wrong_identity)
    await h.due()
    assert await h.phase() is Phase.DELIVERY_UNKNOWN
    assert not h.adapter.calls.count("resume")


async def test_successful_activity_strips_superseded_inline_prompt():
    h = await make_harness()
    await h.due()
    current = await h.runtime.for_conversation(h.key).current()
    await h.runtime.for_conversation(h.key).touch(expected=current.guard, operation_id="text")
    assert len(h.presenter.strips) == 1
    assert await h.phase() is Phase.ACTIVE


async def test_maximum_length_operation_id_can_complete_control():
    h = await make_harness()
    await h.due()
    result = await h.answer(operation_id="x" * 256)
    assert result.outcome == "continued"
    assert await h.phase() is Phase.ACTIVE


async def test_epoch_zero_draft_expiry_is_not_treated_as_missing():
    h = await make_harness()
    h.adapter.eligibility = replace(h.adapter.eligibility, expires_at=0)
    await h.due()
    assert not h.presenter.questions
    assert await h.phase() is Phase.DISARMED


async def test_disabled_fsm_raw_state_is_reloaded_after_idle_lock(monkeypatch):
    from aiogram import Bot, Dispatcher
    from aiogram.filters import StateFilter
    from aiogram.types import Update

    from aiogram_idle.integration import install
    from tests.test_telegram import FakeRuntime, message

    bot = Bot("123456:ABC")
    dp = Dispatcher()
    runtime = FakeRuntime(bot)
    install(runtime, dp, lifecycle=False)
    first_entered = asyncio.Event()
    second_loaded = asyncio.Event()
    release = asyncio.Event()
    calls = []
    original = dp.storage.get_state
    reads = 0

    async def read(key):
        nonlocal reads
        value = await original(key)
        reads += 1
        if reads == 3:
            second_loaded.set()
        return value

    monkeypatch.setattr(dp.storage, "get_state", read)

    @dp.message(StateFilter(None))
    async def first_handler(message, state):
        calls.append("first")
        first_entered.set()
        await release.wait()
        await state.set_state("done")

    @dp.message(StateFilter("done"))
    async def done_handler(message):
        calls.append("done")

    first = asyncio.create_task(dp.feed_update(bot, Update(update_id=1, message=message())))
    await asyncio.wait_for(first_entered.wait(), 2)
    second = asyncio.create_task(
        dp.feed_update(bot, Update(update_id=2, message=message(message_id=2)))
    )
    await asyncio.wait_for(second_loaded.wait(), 2)
    release.set()
    await asyncio.gather(first, second)
    assert calls == ["first", "done"]
    await dp.fsm.close()
    await bot.session.close()
