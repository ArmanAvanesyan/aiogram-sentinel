"""Worker lifetime, recovery and public admission edge cases."""

import asyncio

import pytest

from aiogram_idle.config import IdleConfig
from aiogram_idle.controls import ControlContext
from aiogram_idle.errors import ConfigurationError
from aiogram_idle.models import FlowEligibility, Phase
from aiogram_idle.runtime import IdleRuntime
from tests.runtime_helpers import make_harness


async def test_managed_start_stop_is_idempotent_and_restartable() -> None:
    h = await make_harness()
    await h.runtime.start()
    first = h.runtime._task
    await h.runtime.start()
    assert first is h.runtime._task
    for _ in range(20):
        await asyncio.sleep(0)
    stopping = asyncio.create_task(h.runtime.stop())
    await asyncio.sleep(0)
    h.clock.advance(10)
    await asyncio.wait_for(stopping, 1)
    assert h.runtime._task is None
    assert not (await h.runtime.run_once()).claimed
    await h.runtime.stop()
    await h.runtime.start()
    for _ in range(20):
        await asyncio.sleep(0)
    stopping = asyncio.create_task(h.runtime.stop())
    await asyncio.sleep(0)
    h.clock.advance(10)
    await asyncio.wait_for(stopping, 1)


async def test_worker_renews_claim_while_question_waits_for_response() -> None:
    h = await make_harness()
    h.presenter.show_entered, h.presenter.show_release = asyncio.Event(), asyncio.Event()
    h.clock.advance(10)
    running = asyncio.create_task(h.runtime.run_once())
    await h.presenter.show_entered.wait()
    h.clock.advance(h.runtime.config.renew_seconds)
    for _ in range(10):
        await asyncio.sleep(0)
    h.presenter.show_release.set()
    report = await asyncio.wait_for(running, 1)
    assert report.completed == 1
    assert await h.phase() is Phase.PROMPTED
    assert len(h.presenter.questions) == 1


async def test_rejected_continue_restores_instead_of_exposing_revoked_draft() -> None:
    h = await make_harness()
    await h.due()
    h.adapter.eligibility = FlowEligibility(authorized=False)
    answer = await h.answer()
    assert answer.accepted
    assert "resume" not in h.adapter.calls
    assert "abandon:expired" in h.adapter.calls
    assert "restore:expired" in h.adapter.calls
    assert await h.phase() is Phase.DISARMED


async def test_unknown_outcome_send_does_not_repeat_resume() -> None:
    h = await make_harness()
    h.presenter.finish_error = ConnectionError("outcome response lost")
    await h.due()
    await h.answer()
    assert await h.phase() is Phase.EFFECT_UNKNOWN
    assert h.adapter.calls.count("resume") == 1
    await h.due(100)
    assert h.adapter.calls.count("resume") == 1
    assert len(h.presenter.finishes) == 1


async def test_missing_conversation_and_wrong_prompt_controls_are_inert() -> None:
    h = await make_harness()
    assert not (await h.runtime.continue_current(ControlContext(h.key, 2))).accepted
    await h.due()
    result = await h.runtime.cancel_current(ControlContext(h.key, 2, prompt_id="old"))
    assert not result.accepted
    assert h.adapter.calls == ["inspect"]


async def test_runtime_constructor_rejects_empty_namespace_or_adapters() -> None:
    h = await make_harness()
    for options in [{"namespace": ""}, {"adapters": {}}]:
        kwargs = {
            "backend": h.backend,
            "policies": h.runtime.policies,
            "adapters": {"form": h.adapter},
            "presenter": h.presenter,
            "namespace": "test",
            **options,
        }
        with pytest.raises(ConfigurationError):
            IdleRuntime(**kwargs)


async def test_current_returns_none_after_logical_session_expiry() -> None:
    h = await make_harness(lifetime=10)
    h.clock.advance(11)
    assert await h.runtime.for_conversation(h.key).current() is None


async def test_activity_guarded_clear_and_session_replace_use_public_context() -> None:
    h = await make_harness()
    context = h.runtime.for_conversation(h.key)
    old = await h.runtime.inspect(h.key)
    assert old is not None
    await context.clear(expected=h.activity.guard, reason="complete", operation_id="clear")
    assert await context.current() is None
    replaced = await context.replace_session(
        expected=old.session.guard, operation_id="replace-session", lifetime_seconds=200
    )
    assert replaced.session_id != old.session.session_id
    assert replaced.expires_at == 1200


async def test_dependencies_are_resolved_for_background_effects() -> None:
    h = await make_harness()
    keys = []

    async def dependencies(key):
        keys.append(key)
        return {"service": "example"}

    h.runtime.dependencies = dependencies
    await h.due()
    await h.answer()
    assert keys == [h.key, h.key]


async def test_lost_lease_cancels_slow_question_and_recovery_never_resends() -> None:
    h = await make_harness()
    h.presenter.show_entered, h.presenter.show_release = asyncio.Event(), asyncio.Event()
    h.clock.advance(10)
    running = asyncio.create_task(h.runtime.run_once())
    await h.presenter.show_entered.wait()
    h.clock.advance(h.runtime.config.lease_seconds + 1)
    report = await asyncio.wait_for(running, 1)
    assert report.failed == 1
    await h.runtime.run_once()
    assert await h.phase() is Phase.DELIVERY_UNKNOWN
    assert len(h.presenter.questions) == 1
    assert not any(call.startswith("abandon") for call in h.adapter.calls)


async def test_operation_timeout_retains_started_effect_for_next_poll() -> None:
    h = await make_harness(config=IdleConfig(enabled=True, operation_timeout_seconds=0.01))
    h.presenter.show_entered, h.presenter.show_release = asyncio.Event(), asyncio.Event()
    h.clock.advance(10)
    report = await h.runtime.run_once()
    assert report.failed == 1
    record = await h.runtime.inspect(h.key)
    assert record is not None and record.idle.operation is not None
    assert record.idle.operation.effects["question"] == "started"
    await h.runtime.run_once()
    assert await h.phase() is Phase.DELIVERY_UNKNOWN
    assert len(h.presenter.questions) == 1


async def test_lock_contention_does_not_send_under_another_handler() -> None:
    h = await make_harness(config=IdleConfig(enabled=True, lock_wait_seconds=0.01))
    h.clock.advance(10)
    async with h.runtime.coordinator.hold(h.key):
        report = await h.runtime.run_once()
        assert report.failed == 1
        assert not h.presenter.questions
    await h.runtime.run_once()
    assert await h.phase() is Phase.PROMPTED


async def test_failed_preflight_is_retryable_without_claiming_delivery_unknown() -> None:
    h = await make_harness()
    h.adapter.inspect_errors.append(ConnectionError("dependency lookup failed"))
    await h.due()
    assert await h.phase() is Phase.PROMPT_PENDING
    assert not h.presenter.questions
    await h.due()
    assert await h.phase() is Phase.PROMPTED
    assert len(h.presenter.questions) == 1


async def test_unknown_transport_cannot_bypass_inline_token_guards() -> None:
    h = await make_harness()
    await h.due()
    result = await h.runtime.continue_current(
        ControlContext(h.key, 2, transport="Inline", token="bad", operation_id="wrong-transport")
    )
    assert not result.accepted
    assert h.adapter.calls == ["inspect"]


async def test_runtime_cannot_answer_activity_owned_by_another_namespace() -> None:
    h = await make_harness()
    await h.due()
    other = IdleRuntime(
        backend=h.backend,
        policies=h.runtime.policies,
        adapters={"form": h.adapter},
        presenter=h.presenter,
        namespace="other",
        isolation=h.runtime.coordinator,
    )
    result = await other.continue_current(ControlContext(h.key, 2))
    assert not result.accepted
    assert h.adapter.calls == ["inspect"]


async def test_failed_resume_preflight_retries_without_replaying_any_effect() -> None:
    h = await make_harness()
    await h.due()
    h.adapter.inspect_errors.append(ConnectionError("authorization lookup failed"))
    assert (await h.answer()).accepted
    assert await h.phase() is Phase.RESUMING
    assert "resume" not in h.adapter.calls
    await h.due()
    assert await h.phase() is Phase.ACTIVE
    assert h.adapter.calls.count("resume") == 1
