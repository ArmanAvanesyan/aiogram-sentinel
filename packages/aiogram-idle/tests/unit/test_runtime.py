"""End-to-end memory runtime tests with deterministic time and effect barriers."""

import asyncio

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage

from aiogram_idle.config import AmbiguousSendPolicy, IdleConfig
from aiogram_idle.controls import ControlContext
from aiogram_idle.errors import ActivityConflict, ConfigurationError, ConfigurationMismatch
from aiogram_idle.models import (
    ActionReceipt,
    ActivitySpec,
    ConfigUpdate,
    FlowEligibility,
    IdleConversationKey,
    Phase,
)
from aiogram_idle.policies import ExemptPolicy, IdlePolicies, QuietRestorePolicy
from aiogram_idle.runtime import IdleRuntime
from tests.runtime_helpers import make_harness


async def test_full_continue_cycle_keeps_draft_and_rearms_from_answer_time() -> None:
    h = await make_harness()
    report = await h.due()
    assert report.claimed == report.completed == 1
    assert await h.phase() is Phase.PROMPTED
    prompt = await h.runtime.current_prompt(h.key)
    assert prompt is not None
    assert prompt.messages[0].message_id == 100
    assert len(h.presenter.questions) == 1
    h.clock.advance(3)
    result = await h.answer(transport="inline")
    assert result.accepted and result.outcome == "continued"
    record = await h.runtime.inspect(h.key)
    assert record is not None and record.activity is not None
    assert record.idle.phase is Phase.ACTIVE
    assert record.idle.deadline == 1023
    assert record.activity.activity_id == h.activity.activity_id
    assert record.activity.activity_revision == 2
    assert record.activity.params == h.activity.params
    assert record.session.expires_at == 2000
    assert h.adapter.calls == ["inspect", "inspect", "resume"]
    assert [finish.outcome for finish in h.presenter.finishes] == ["continued"]


@pytest.mark.parametrize("action", ["cancel", "timeout"])
async def test_cancel_and_grace_timeout_abandon_and_restore(action: str) -> None:
    h = await make_harness()
    await h.due()
    if action == "cancel":
        assert (await h.answer("cancel")).accepted
    else:
        report = await h.due(20)
        assert report.completed == 1
    assert await h.phase() is Phase.DISARMED
    assert sum(call.startswith("abandon:") for call in h.adapter.calls) == 1
    assert sum(call.startswith("restore:") for call in h.adapter.calls) == 1
    assert len(h.presenter.finishes) == 1
    assert not (await h.runtime.run_once()).claimed


async def test_quiet_restore_uses_no_question() -> None:
    h = await make_harness(policy=QuietRestorePolicy(after_seconds=10))
    await h.due()
    assert await h.phase() is Phase.DISARMED
    assert not h.presenter.questions
    assert h.adapter.calls == ["abandon:restored", "restore:restored"]


async def test_disabled_then_enable_requires_new_activity_and_exempt_stays_disarmed() -> None:
    h = await make_harness(enabled=False)
    assert await h.phase() is Phase.DISARMED
    assert not (await h.due(100)).claimed
    manifest = await h.backend.get_config()
    assert manifest is not None
    updated = await h.runtime.apply_config(
        expected_generation=manifest.generation, update=ConfigUpdate(True, "enable")
    )
    assert updated.enabled
    assert not (await h.runtime.run_once()).claimed
    activity = await h.runtime.for_conversation(h.key).touch(
        expected=h.activity.guard, operation_id="accept"
    )
    await h.due()
    assert await h.phase() is Phase.PROMPTED
    await h.runtime.for_conversation(h.key).enter(
        "read.only",
        policy_id="skip",
        adapter_key="form",
        params={"draft_id": "draft"},
        session_id=activity.session_id,
        expires_at=activity.expires_at,
        expected=activity.guard,
        operation_id="exempt",
    )
    assert await h.phase() is Phase.DISARMED


async def test_disablement_does_not_cancel_existing_grace() -> None:
    h = await make_harness()
    await h.due()
    manifest = await h.backend.get_config()
    assert manifest is not None
    await h.runtime.apply_config(
        expected_generation=manifest.generation, update=ConfigUpdate(False, "disable")
    )
    await h.due(20)
    assert await h.phase() is Phase.DISARMED
    assert "abandon:timed_out" in h.adapter.calls


@pytest.mark.parametrize(
    "eligibility",
    [
        FlowEligibility(authorized=False),
        FlowEligibility(resumable=False),
        FlowEligibility(expires_at=1015),
    ],
)
async def test_ineligible_flow_is_restored_without_question(eligibility: FlowEligibility) -> None:
    h = await make_harness()
    h.adapter.eligibility = eligibility
    await h.due()
    assert not h.presenter.questions
    assert await h.phase() is Phase.DISARMED
    assert "abandon:expired" in h.adapter.calls


async def test_short_session_never_gets_truncated_grace() -> None:
    h = await make_harness(lifetime=25)
    await h.due()
    assert not h.presenter.questions
    assert await h.phase() is Phase.DISARMED


async def test_expired_session_drops_work_and_rejects_controls() -> None:
    h = await make_harness(lifetime=5)
    await h.due(10)
    assert not h.presenter.questions
    assert await h.phase() is Phase.DISARMED
    assert not (await h.runtime.continue_current(ControlContext(h.key, 2))).accepted


async def test_unknown_question_is_not_resent_or_auto_abandoned() -> None:
    h = await make_harness()
    h.presenter.show_errors.append(ConnectionError("response was lost"))
    await h.due()
    assert await h.phase() is Phase.DELIVERY_UNKNOWN
    assert len(h.presenter.questions) == 1
    await h.due(100)
    assert len(h.presenter.questions) == 1
    assert h.adapter.calls == ["inspect"]
    # A token from the accepted-but-unacknowledged question can prove receipt.
    assert (await h.answer(transport="inline")).accepted
    assert await h.phase() is Phase.ACTIVE


async def test_retry_after_retries_only_after_server_deadline() -> None:
    h = await make_harness()
    h.presenter.show_errors.append(
        TelegramRetryAfter(
            method=SendMessage(chat_id=2, text="question"), message="retry", retry_after=7
        )
    )
    await h.due()
    assert await h.phase() is Phase.PROMPT_PENDING
    assert len(h.presenter.questions) == 1
    assert not (await h.due(6)).claimed
    await h.due(1)
    assert len(h.presenter.questions) == 2
    assert await h.phase() is Phase.PROMPTED
    record = await h.runtime.inspect(h.key)
    assert record is not None and record.idle.deadline == 1037


async def test_retry_budget_exhaustion_and_forbidden_are_quarantined() -> None:
    h = await make_harness(config=IdleConfig(enabled=True, retry_max_attempts=1))
    h.presenter.show_errors.append(
        TelegramRetryAfter(
            method=SendMessage(chat_id=2, text="question"), message="retry", retry_after=7
        )
    )
    await h.due()
    assert await h.phase() is Phase.QUARANTINED
    other = await make_harness()
    other.presenter.show_errors.append(
        TelegramForbiddenError(method=SendMessage(chat_id=2, text="question"), message="blocked")
    )
    await other.due()
    assert await other.phase() is Phase.QUARANTINED
    assert not any(call.startswith("abandon") for call in other.adapter.calls)


async def test_explicit_ambiguous_retry_is_bounded() -> None:
    h = await make_harness(
        config=IdleConfig(
            enabled=True, retry_max_attempts=2, ambiguous_send=AmbiguousSendPolicy.RETRY
        )
    )
    h.presenter.show_errors.extend([ConnectionError(), ConnectionError()])
    await h.due()
    assert await h.phase() is Phase.PROMPT_PENDING
    await h.due()
    assert await h.phase() is Phase.QUARANTINED
    assert len(h.presenter.questions) == 2


async def test_wrong_actor_token_prompt_and_message_never_run_business_effects() -> None:
    h = await make_harness()
    await h.due()
    prompt = await h.runtime.current_prompt(h.key)
    assert prompt is not None
    contexts = [
        ControlContext(h.key, 3),
        ControlContext(h.key, 2, prompt_id="old"),
        ControlContext(h.key, 2, transport="inline", token="bad", message_id=100),
        ControlContext(h.key, 2, transport="inline", token=prompt.continue_token, message_id=999),
    ]
    for context in contexts:
        assert not (await h.runtime.continue_current(context)).accepted
    assert h.adapter.calls == ["inspect"]


async def test_duplicate_answer_and_continue_cancel_race_do_not_repeat_adapter() -> None:
    h = await make_harness()
    await h.due()
    prompt = await h.runtime.current_prompt(h.key)
    assert prompt is not None
    answers = await asyncio.gather(
        h.runtime.continue_current(
            ControlContext(h.key, 2, prompt_id=prompt.prompt_id, operation_id="answer")
        ),
        h.runtime.cancel_current(
            ControlContext(h.key, 2, prompt_id=prompt.prompt_id, operation_id="cancel")
        ),
    )
    assert sum(answer.accepted for answer in answers) == 1
    assert sum(call == "resume" for call in h.adapter.calls) <= 1
    assert not (await h.runtime.continue_current(ControlContext(h.key, 2))).accepted


async def test_two_runtimes_share_one_backend_and_do_not_double_prompt() -> None:
    h = await make_harness()
    other = IdleRuntime(
        backend=h.backend,
        policies=h.runtime.policies,
        adapters={"form": h.adapter},
        presenter=h.presenter,
        namespace="test",
        isolation=h.runtime.coordinator,
    )
    other.bot = None
    h.clock.advance(10)
    reports = await asyncio.gather(h.runtime.run_once(), other.run_once())
    assert sum(report.claimed for report in reports) == 1
    assert len(h.presenter.questions) == 1


async def test_confirmed_abandon_is_not_repeated_after_restore_response_lost() -> None:
    h = await make_harness()
    h.adapter.restore_error = ConnectionError("unknown restore")
    await h.due()
    assert (await h.answer("cancel")).accepted
    assert await h.phase() is Phase.EFFECT_UNKNOWN
    assert h.adapter.calls.count("abandon:cancelled") == 1
    await h.due(100)
    assert h.adapter.calls.count("abandon:cancelled") == 1
    assert h.adapter.calls.count("restore:cancelled") == 1


async def test_cancellation_leaves_started_stage_as_recovery_evidence() -> None:
    h = await make_harness(policy=QuietRestorePolicy(after_seconds=10))
    h.adapter.restore_entered, h.adapter.restore_release = asyncio.Event(), asyncio.Event()
    h.clock.advance(10)
    task = asyncio.create_task(h.runtime.run_once())
    await h.adapter.restore_entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    record = await h.runtime.inspect(h.key)
    assert record is not None and record.idle.operation is not None
    assert record.idle.operation.effects["abandon"] == "confirmed"
    assert record.idle.operation.effects["restore"] == "started"
    await h.runtime.run_once()
    assert await h.phase() is Phase.EFFECT_UNKNOWN
    assert h.adapter.calls.count("abandon:restored") == 1


async def test_adapter_replacement_commits_new_generation_atomically() -> None:
    h = await make_harness()
    h.adapter.resume_result = ActionReceipt(
        disposition="replacement",
        replacement=ActivitySpec("second.step", "skip", "form", {"draft_id": "draft"}),
    )
    await h.due()
    await h.answer()
    record = await h.runtime.inspect(h.key)
    assert record is not None and record.activity is not None
    assert record.activity.activity_key == "second.step"
    assert record.activity.activity_id != h.activity.activity_id
    assert record.idle.phase is Phase.DISARMED


async def test_hook_failure_cannot_repeat_committed_question() -> None:
    events = []

    async def hook(event):
        events.append(event)
        raise RuntimeError("analytics down")

    h = await make_harness(on_event=hook)
    await h.due()
    assert await h.phase() is Phase.PROMPTED
    assert len(events) == len(h.presenter.questions) == 1
    await h.runtime.run_once()
    assert len(h.presenter.questions) == 1


async def test_successful_touch_supersedes_prompt_and_stale_guard_cannot_retouch() -> None:
    h = await make_harness()
    await h.due()
    result = await h.runtime.for_conversation(h.key).touch(
        expected=h.activity.guard, operation_id="draft-text"
    )
    assert result.activity_revision == 2
    assert await h.phase() is Phase.ACTIVE
    assert await h.runtime.current_prompt(h.key) is None
    with pytest.raises(ActivityConflict):
        await h.runtime.for_conversation(h.key).touch(
            expected=h.activity.guard, operation_id="old-text"
        )


async def test_configuration_and_namespace_errors_are_actionable() -> None:
    h = await make_harness()
    with pytest.raises(ConfigurationError):
        h.runtime.for_conversation(IdleConversationKey("wrong", 1, 2, 2))
    with pytest.raises(ConfigurationError):
        h.runtime.adapter("missing")
    other = IdleRuntime(
        backend=h.backend,
        policies=IdlePolicies({"other": ExemptPolicy()}),
        adapters={"form": h.adapter},
        presenter=h.presenter,
        namespace="test",
    )
    with pytest.raises(ConfigurationMismatch):
        await other.initialize()
    with pytest.raises(ValueError):
        await h.runtime.run_once(limit=0)
    assert (await h.runtime.reconcile()).repaired >= 0
