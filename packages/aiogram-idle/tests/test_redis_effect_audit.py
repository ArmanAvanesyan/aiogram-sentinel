"""Cross-backend recovery regressions found during the Redis audit."""

from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from aiogram_idle import ActivityConflict, IdleConfig, Phase
from aiogram_idle.effects import OperationEffects
from aiogram_idle.storage.redis import RedisIdleBackend
from tests.runtime_helpers import Adapter, Presenter, make_harness
from tests.test_redis_backend import make_due, seed
from tests.test_redis_recovery import runtime


@pytest.mark.parametrize("backend_kind", ["memory", "redis"])
@pytest.mark.parametrize("forbidden", [False, True])
async def test_unknown_business_operation_blocks_new_input(redis_client, backend_kind, forbidden):
    if backend_kind == "memory":
        harness = await make_harness()
        idle, backend, adapter, key = harness.runtime, harness.backend, harness.adapter, harness.key
        await harness.due()
    else:
        backend = RedisIdleBackend(
            redis=redis_client,
            prefix=f"effect-audit:{uuid4().hex}",
            config=IdleConfig(enabled=True),
        )
        await backend.initialize()
        adapter = Adapter()
        idle = runtime(backend, adapter, Presenter(backend.clock))
        await idle.initialize()
        key, _, _ = await seed(backend)
        await make_due(backend, key)
        await idle.run_once()
    adapter.resume_error = (
        TelegramForbiddenError(
            method=SendMessage(chat_id=key.chat_id, text="resume"), message="blocked"
        )
        if forbidden
        else TimeoutError("business response uncertain")
    )
    from aiogram_idle import ControlContext

    prompt = await idle.current_prompt(key)
    await idle.continue_current(
        ControlContext(key, key.user_id, prompt_id=prompt.prompt_id, operation_id="answer")
    )
    saved = await backend.load(key)
    assert saved.idle.phase is (Phase.QUARANTINED if forbidden else Phase.EFFECT_UNKNOWN)
    assert await idle.is_busy(key)
    context = idle.for_conversation(key)
    for action in [
        context.touch(expected=saved.activity.guard, operation_id="touch"),
        context.clear(expected=saved.activity.guard, operation_id="clear", reason="new input"),
        context.enter(
            "new",
            policy_id="draft",
            adapter_key="form",
            params={},
            session_id=saved.session.session_id,
            expires_at=saved.session.expires_at,
            expected=saved.activity.guard,
            operation_id="enter-new",
        ),
    ]:
        with pytest.raises(ActivityConflict):
            await action
    assert (await backend.load(key)).idle.operation == saved.idle.operation


async def test_question_rechecks_remaining_grace_after_control_checkpoints(monkeypatch):
    harness = await make_harness(lifetime=40)
    reserve = harness.backend.reserve_control
    advanced = False

    async def delayed(*args, **kwargs):
        nonlocal advanced
        result = await reserve(*args, **kwargs)
        if not advanced:
            advanced = True
            harness.clock.advance(15)
        return result

    monkeypatch.setattr(harness.backend, "reserve_control", delayed)
    await harness.due()
    assert harness.presenter.questions == []
    assert await harness.phase() is Phase.DISARMED
    assert "restore:expired" in harness.adapter.calls


async def test_question_rechecks_grace_at_nested_telegram_send(monkeypatch):
    harness = await make_harness(lifetime=40)
    checkpoint = OperationEffects.checkpoint
    sent = []

    async def delayed(self, stage, state, result=None):
        await checkpoint(self, stage, state, result)
        if stage == "question-message" and state == "started":
            harness.clock.advance(15)

    async def show(request):
        async def send():
            sent.append("sent")
            return None

        await request.effects.run("question-message", send)
        raise AssertionError("insufficient lifetime must stop before sending")

    monkeypatch.setattr(OperationEffects, "checkpoint", delayed)
    monkeypatch.setattr(harness.presenter, "show", show)
    await harness.due()
    assert sent == []
    assert await harness.phase() is Phase.DISARMED
    assert "restore:expired" in harness.adapter.calls


async def test_receipt_for_another_business_operation_cannot_rearm():
    from aiogram_idle import ActionReceipt

    harness = await make_harness()
    await harness.due()
    harness.adapter.resume_result = ActionReceipt(operation_id="another-operation")
    await harness.answer()
    saved = await harness.backend.load(harness.key)
    assert saved.idle.phase is Phase.EFFECT_UNKNOWN
    assert saved.idle.operation.effects["resume"] == "started"
    assert await harness.runtime.is_busy(harness.key)


async def test_delegated_effect_checkpoint_is_atomically_fenced(redis_client):
    import asyncio
    import hashlib

    from aiogram_idle import ActionReceipt, ControlContext, OwnershipLost
    from aiogram_idle.storage.redis_scripts import COMMIT

    class Intercept:
        lock = ""
        stolen = False

        async def execute_command(self, *args):
            if (
                args[0] == "EVALSHA"
                and args[1] == hashlib.sha1(COMMIT.encode(), usedforsecurity=False).hexdigest()
                and not self.stolen
                and any(
                    isinstance(arg, str) and ('"child-stage"' in arg or '\\"child-stage\\"' in arg)
                    for arg in args[3:]
                )
            ):
                self.stolen = True
                await redis_client.set(self.lock, "successor", px=30000)
            return await redis_client.execute_command(*args)

    client = Intercept()
    backend = RedisIdleBackend(
        redis=client, prefix=f"delegated-audit:{uuid4().hex}", config=IdleConfig(enabled=True)
    )
    await backend.initialize()
    adapter = Adapter()
    idle = runtime(backend, adapter, Presenter(backend.clock))
    await idle.initialize()
    key, _, _ = await seed(backend)
    client.lock = backend.coordinator.lock_key(key)
    await make_due(backend, key)
    await idle.run_once()
    sent = []

    async def resume(context, *, operation_id):
        async def send():
            sent.append("sent")
            return {"delivered": True}

        # Delegated stages are supported, but never own/bypass the parent lock.
        await asyncio.create_task(context.effects.run("child-stage", send))
        return ActionReceipt(operation_id=operation_id)

    adapter.resume = resume
    prompt = await idle.current_prompt(key)
    with pytest.raises(OwnershipLost):
        await idle.continue_current(
            ControlContext(key, key.user_id, prompt_id=prompt.prompt_id, operation_id="answer")
        )
    assert client.stolen
    assert sent == []
    record = await backend.load(key)
    assert "child-stage" not in record.idle.operation.effects
