"""Independent review regressions for scheduling and recorded effect ownership."""

from __future__ import annotations

import asyncio

import pytest

from aiogram_idle import ActionReceipt, DeliveryReceipt, MessageRef, Phase
from aiogram_idle.effects import OperationEffects
from tests.runtime_helpers import make_harness


async def test_recover_saved_question_keeps_original_grace_near_session_expiry(monkeypatch):
    h = await make_harness(lifetime=40)
    checkpoint = OperationEffects.checkpoint

    async def interrupt(self, stage, state, result=None):
        if stage == "question" and state == "confirmed":
            raise asyncio.CancelledError
        await checkpoint(self, stage, state, result)

    monkeypatch.setattr(OperationEffects, "checkpoint", interrupt)
    with pytest.raises(asyncio.CancelledError):
        await h.due()
    record = await h.runtime.inspect(h.key)
    assert record.idle.prompt.messages
    assert record.idle.prompt.shown_at == 1010
    h.clock.advance(15)
    monkeypatch.setattr(OperationEffects, "checkpoint", checkpoint)
    await h.runtime.run_once()
    record = await h.runtime.inspect(h.key)
    assert record.idle.phase is Phase.PROMPTED
    assert record.idle.deadline == 1030
    assert not any(call.startswith("abandon") for call in h.adapter.calls)
    assert len(h.presenter.questions) == 1


async def test_concurrent_same_stage_effect_has_one_execution(monkeypatch):
    h = await make_harness()
    await h.due()
    checkpoint = OperationEffects.checkpoint
    barrier = asyncio.Event()
    reservations = 0
    sent = 0

    async def synchronized(self, stage, state, result=None):
        nonlocal reservations
        if stage == "app:send" and state == "started":
            reservations += 1
            if reservations == 1:
                asyncio.get_running_loop().call_soon(barrier.set)
            await asyncio.wait_for(barrier.wait(), 2)
        await checkpoint(self, stage, state, result)

    async def resume(context, *, operation_id):
        async def send():
            nonlocal sent
            sent += 1
            return {"sent": True}

        await asyncio.gather(
            context.effects.run("app:send", send),
            context.effects.run("app:send", send),
        )
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(OperationEffects, "checkpoint", synchronized)
    monkeypatch.setattr(h.adapter, "resume", resume)
    await h.answer()
    assert sent == 1


async def test_recorded_delivery_receipt_round_trips_through_effect_recorder(monkeypatch):
    h = await make_harness()
    await h.due()
    receipts = []
    calls = 0

    async def resume(context, *, operation_id):
        async def deliver():
            nonlocal calls
            calls += 1
            return DeliveryReceipt(messages=(MessageRef(h.key.chat_id, 99),), unavailable=True)

        receipts.append(await context.effects.run("app:receipt", deliver))
        receipts.append(await context.effects.run("app:receipt", deliver))
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", resume)
    await h.answer()
    assert calls == 1
    assert receipts[0] == receipts[1]
    assert receipts[1].unavailable


async def test_continue_cannot_extend_grace_after_deadline_without_poller():
    h = await make_harness()
    await h.due()
    from aiogram_idle import ControlContext

    prompt = await h.runtime.current_prompt(h.key)
    h.clock.advance(21)
    result = await h.runtime.continue_current(
        ControlContext(
            key=h.key,
            actor_id=h.key.user_id,
            prompt_id=prompt.prompt_id,
            operation_id="late-answer",
        )
    )
    assert not result.accepted
    assert "resume" not in h.adapter.calls


async def test_captured_recorder_cannot_attach_to_new_generation_reusing_operation_id(monkeypatch):
    from aiogram_idle import OwnershipLost

    h = await make_harness(lifetime=10_000)
    old_recorder = None
    sent = 0

    async def capture(context, *, operation_id):
        nonlocal old_recorder
        old_recorder = context.effects
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", capture)
    await h.due()
    await h.answer(operation_id="answer")
    # Let the first answer's deduplication receipt expire, while keeping the
    # logical session live. Re-entering still creates a different activity_id.
    h.clock.advance(3601)
    current = await h.runtime.for_conversation(h.key).current()
    await h.runtime.for_conversation(h.key).enter(
        "form.entry",
        policy_id="draft",
        adapter_key="form",
        params={"draft_id": "draft"},
        session_id=current.session_id,
        expires_at=current.expires_at,
        expected=current.guard,
        operation_id="new-entry",
    )

    async def attempt_stale_effect(context, *, operation_id):
        async def send():
            nonlocal sent
            sent += 1
            return {"sent": True}

        with pytest.raises(OwnershipLost):
            await old_recorder.run("stale-activity-send", send)
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", attempt_stale_effect)
    await h.due()
    await h.answer(operation_id="answer")
    assert sent == 0


async def test_forbidden_delivery_is_terminal_even_with_ambiguous_retry_policy():
    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.methods import SendMessage

    from aiogram_idle import AmbiguousSendPolicy, IdleConfig

    h = await make_harness(
        config=IdleConfig(enabled=True, ambiguous_send=AmbiguousSendPolicy.RETRY)
    )
    h.presenter.show_errors.append(
        TelegramForbiddenError(
            method=SendMessage(chat_id=h.key.chat_id, text="question"),
            message="blocked",
        )
    )
    await h.due()
    assert await h.phase() is Phase.QUARANTINED
    await h.due(100)
    assert len(h.presenter.questions) == 1
