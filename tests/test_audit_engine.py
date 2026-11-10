"""Cross-module invariants required before a remote backend can be introduced."""

from __future__ import annotations

import asyncio

import pytest
from aiogram import Bot

from aiogram_idle import ActionReceipt, IdleRuntime, OwnershipLost, Phase
from tests.runtime_helpers import Adapter, Presenter, make_harness


async def test_replay_safe_adapter_recovers_confirmed_nested_effect_once(monkeypatch):
    h = await make_harness()
    await h.due()
    sent = 0
    attempts = 0
    h.adapter.replay_safe = True

    async def resume(context, *, operation_id):
        nonlocal sent, attempts

        async def send():
            nonlocal sent
            sent += 1
            return {"receipt": sent}

        result = await context.effects.run("app:send", send)
        assert result == {"receipt": 1}
        attempts += 1
        if attempts == 1:
            raise asyncio.CancelledError
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", resume)
    with pytest.raises(asyncio.CancelledError):
        await h.answer()
    assert await h.phase() is Phase.RESUMING
    await h.runtime.run_once()
    assert await h.phase() is Phase.ACTIVE
    assert sent == 1 and attempts == 2


async def test_recorded_prompt_and_json_receipts_cannot_collide(monkeypatch):
    h = await make_harness()
    await h.due()
    prompt = await h.runtime.current_prompt(h.key)
    seen = []
    value = {"_type": "action", "kind": "action", "value": {"domain": True}}

    async def resume(context, *, operation_id):
        async def json_result():
            return value

        async def prompt_result():
            return prompt

        seen.append(await context.effects.run("app:json", json_result))
        seen.append(await context.effects.run("app:json", json_result))
        seen.append(await context.effects.run("app:prompt", prompt_result))
        seen.append(await context.effects.run("app:prompt", prompt_result))
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", resume)
    await h.answer()
    assert seen[:2] == [value, value]
    assert seen[2:] == [prompt, prompt]


async def test_recorder_cannot_send_after_activity_expires(monkeypatch):
    h = await make_harness()
    await h.due()
    sent = 0

    async def resume(context, *, operation_id):
        h.clock.advance(1000)

        async def send():
            nonlocal sent
            sent += 1
            return None

        await context.effects.run("app:late-send", send)
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", resume)
    with pytest.raises(OwnershipLost):
        await h.answer()
    await h.runtime.run_once()
    record = await h.runtime.inspect(h.key)
    assert record.idle.phase is Phase.QUARANTINED
    assert record.idle.operation.failure_reason == "logical_expiry"
    assert sent == 0


@pytest.mark.parametrize("foreign_namespace,foreign_bot", [("foreign", 1), ("test", 9)])
async def test_runtime_does_not_claim_foreign_application_jobs(foreign_namespace, foreign_bot):
    from aiogram_idle import IdleConversationKey

    h = await make_harness()
    other_presenter = Presenter(h.clock)
    other = IdleRuntime(
        backend=h.backend,
        policies=h.runtime.policies,
        adapters={"form": Adapter()},
        presenter=other_presenter,
        namespace=foreign_namespace,
        bot=Bot(f"{foreign_bot}:ABC"),
    )
    h.runtime.bot = Bot("1:ABC")
    key = IdleConversationKey(foreign_namespace, foreign_bot, 3, 3)
    ctx = other.for_conversation(key)
    session = await ctx.open_session(operation_id="open", lifetime_seconds=1000)
    await ctx.enter(
        "form",
        policy_id="draft",
        adapter_key="form",
        params={"draft_id": "draft"},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
    )
    h.clock.advance(10)
    await h.runtime.run_once()
    assert len(h.presenter.questions) == 1
    assert not other_presenter.questions
    await other.run_once()
    assert len(other_presenter.questions) == 1
    await h.runtime.bot.session.close()
    await other.bot.session.close()


async def test_failed_delivery_is_reported_failed_with_safe_diagnostics():
    h = await make_harness()
    h.presenter.show_errors.append(TimeoutError("sensitive payload must not be persisted"))
    report = await h.due()
    assert report.failed == 1 and report.completed == 0
    record = await h.runtime.inspect(h.key)
    assert record.idle.operation.failure_reason == "TimeoutError"
    assert "sensitive" not in repr(record)


async def test_reserved_effect_names_are_rejected_before_an_external_call(monkeypatch):
    h = await make_harness()
    await h.due()
    called = False

    async def resume(context, *, operation_id):
        nonlocal called

        async def send():
            nonlocal called
            called = True

        for name in ("", "result:resume", "x" * 129):
            with pytest.raises(ValueError):
                await context.effects.run(name, send)
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", resume)
    await h.answer()
    assert not called


async def test_managed_loop_survives_transient_backend_failure(monkeypatch):
    h = await make_harness()
    original_claim = h.backend.claim_due
    original_sleep = h.clock.sleep
    sleeping = asyncio.Event()
    attempts = 0
    h.presenter.show_entered = asyncio.Event()

    async def claim(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("transient")
        return await original_claim(**kwargs)

    async def sleep(seconds):
        sleeping.set()
        await original_sleep(seconds)

    monkeypatch.setattr(h.backend, "claim_due", claim)
    monkeypatch.setattr(h.clock, "sleep", sleep)
    await h.runtime.start()
    await asyncio.wait_for(sleeping.wait(), 2)
    h.clock.advance(10)
    await asyncio.wait_for(h.presenter.show_entered.wait(), 2)
    await h.runtime.stop()
    assert attempts >= 2


async def test_parallel_distinct_effect_stages_preserve_all_receipts(monkeypatch):
    h = await make_harness()
    await h.due()
    load = h.backend.load

    async def delayed(key):
        result = await load(key)
        await asyncio.sleep(0)
        return result

    async def resume(context, *, operation_id):
        async def effect():
            await asyncio.sleep(0)
            return {"ok": True}

        results = await asyncio.gather(
            context.effects.run("app:first", effect), context.effects.run("app:second", effect)
        )
        assert results == [{"ok": True}, {"ok": True}]
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.backend, "load", delayed)
    monkeypatch.setattr(h.adapter, "resume", resume)
    result = await h.answer()
    assert result.outcome == "continued"
    assert await h.phase() is Phase.ACTIVE


async def test_unawaited_delegated_effect_is_not_silently_discarded(monkeypatch):
    h = await make_harness()
    await h.due()
    entered = asyncio.Event()
    release = asyncio.Event()
    tasks = []

    async def resume(context, *, operation_id):
        async def send():
            entered.set()
            await release.wait()
            return {"sent": True}

        tasks.append(asyncio.create_task(context.effects.run("app:unawaited", send)))
        await entered.wait()
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", resume)
    try:
        result = await h.answer()
        assert result.outcome == "effect_unknown"
        current = await h.runtime.inspect(h.key)
        assert current.idle.operation.effects["app:unawaited"] == "started"
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


def test_clock_rollback_cannot_make_pruned_history_provably_absent():
    from aiogram_idle.storage.receipts import Receipts, lookup_operation

    receipts = Receipts(limit=10, retention=3600)
    receipts.save("key", "old", "fingerprint", "completed", now=1000)
    receipts.prepare("key", "next", "different", now=4601)
    result = lookup_operation(receipts, "key", "old", now=1010, created_at=1000, not_before=1000)
    assert result.status == "unknown_history"


async def test_standalone_presenter_bot_binds_worker_routing():
    from aiogram_idle import ConfigurationError, TelegramPromptPresenter

    h = await make_harness()
    bot, other = Bot("1:ABC"), Bot("2:ABC")
    try:
        runtime = IdleRuntime(
            backend=h.backend,
            policies=h.runtime.policies,
            adapters={"form": h.adapter},
            presenter=TelegramPromptPresenter(bot),
            namespace="test",
        )
        assert runtime.bot is bot
        with pytest.raises(ConfigurationError):
            IdleRuntime(
                backend=h.backend,
                policies=h.runtime.policies,
                adapters={"form": h.adapter},
                presenter=TelegramPromptPresenter(bot),
                bot=other,
                namespace="test",
            )
    finally:
        await bot.session.close()
        await other.session.close()


async def test_state_commit_failure_preserves_confirmed_restore_receipt(monkeypatch):
    from aiogram_idle import QuietRestorePolicy
    from aiogram_idle.effects import internal_id

    h = await make_harness(policy=QuietRestorePolicy(after_seconds=10))
    transition = h.backend.transition
    rejected = False

    async def fail_completion(key, **kwargs):
        nonlocal rejected
        current = await h.backend.load(key)
        operation = current.idle.operation
        if (
            operation is not None
            and kwargs["operation_id"] == internal_id(operation.operation_id, "complete")
            and not rejected
        ):
            rejected = True
            raise ConnectionError("completion reply lost before commit")
        return await transition(key, **kwargs)

    monkeypatch.setattr(h.backend, "transition", fail_completion)
    await h.due()
    assert await h.phase() is Phase.RESTORING
    await h.due(10)
    assert await h.phase() is Phase.DISARMED
    assert h.adapter.calls.count("restore:restored") == 1
    assert h.adapter.calls.count("abandon:restored") == 1


async def test_replay_safe_aggregate_can_retry_after_recorded_substep(monkeypatch):
    h = await make_harness()
    await h.due()
    h.adapter.replay_safe = True
    sends = 0
    attempts = 0

    async def resume(context, *, operation_id):
        nonlocal attempts

        async def send():
            nonlocal sends
            sends += 1
            return {"message_id": 7}

        await context.effects.run("app:send", send)
        attempts += 1
        if attempts == 1:
            raise ConnectionError("transient pure processing failure after send receipt")
        return ActionReceipt(operation_id=operation_id)

    monkeypatch.setattr(h.adapter, "resume", resume)
    result = await h.answer()
    assert result.outcome == "resuming"
    await h.due(10)
    assert await h.phase() is Phase.ACTIVE
    assert sends == 1 and attempts == 2
