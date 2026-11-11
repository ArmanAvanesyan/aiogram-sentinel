"""Public contracts reject unsafe values and expose detached immutable snapshots."""

import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from types import MappingProxyType

import pytest

from aiogram_idle.clock import ManualClock, SystemClock
from aiogram_idle.config import AmbiguousSendPolicy, IdleConfig
from aiogram_idle.errors import ActivityConflict, ConfigurationError, UnsupportedContext
from aiogram_idle.machine import Trigger, reduce_phase
from aiogram_idle.models import (
    ActionReceipt,
    ActivitySnapshot,
    ActivitySpec,
    FlowContext,
    IdleConversationKey,
    PendingOperation,
    Phase,
    RuntimeSnapshot,
    SessionSnapshot,
    fingerprint,
    freeze_json,
    freeze_object,
    thaw_json,
    timestamp,
)
from aiogram_idle.policies import (
    ExemptPolicy,
    IdlePolicies,
    PromptPolicy,
    QuietRestorePolicy,
    policy_digest,
)


def make_activity() -> ActivitySnapshot:
    return ActivitySnapshot(
        "session",
        "activity",
        "draft",
        1,
        "prompt",
        "form",
        {"items": [{"rating": 5}]},
        100,
        100,
        200,
    )


def test_identity_is_private_and_namespace_and_tenant_are_unambiguous() -> None:
    key = IdleConversationKey("bot", 1, 2, 2)
    assert key != IdleConversationKey("bot", 1, 2, 2, "tenant")
    assert key != IdleConversationKey("other", 1, 2, 2)
    assert key != IdleConversationKey("bot", 3, 2, 2)
    for args in [("", 1, 2, 2), ("a", 0, 2, 2), ("a", 1, -2, 2), ("a", 1, 2, 3), ("a", True, 2, 2)]:
        with pytest.raises(UnsupportedContext):
            IdleConversationKey(*args)
    with pytest.raises(UnsupportedContext):
        IdleConversationKey("bot", 1, 2, 2, "")


def test_json_is_recursively_detached_and_serializable() -> None:
    original = {"rows": [{"answer": 5}], "tuple": (1, None), "flag": True}
    frozen = freeze_object(original)
    original["rows"][0]["answer"] = 9
    assert thaw_json(frozen) == {
        "rows": [{"answer": 5}],
        "tuple": [1, None],
        "flag": True,
    }
    assert isinstance(frozen, MappingProxyType)
    with pytest.raises(TypeError):
        frozen["added"] = 1
    with pytest.raises(TypeError):
        frozen["rows"][0]["answer"] = 1
    assert fingerprint({"b": 2, "a": 1}) == fingerprint({"a": 1, "b": 2})


@pytest.mark.parametrize("value", [float("inf"), float("nan"), object(), {1: "bad"}])
def test_json_rejects_non_json_or_non_finite_values(value: object) -> None:
    with pytest.raises(ConfigurationError):
        freeze_json(value)


def test_json_limits_and_object_requirement() -> None:
    with pytest.raises(ConfigurationError):
        freeze_json("large", max_bytes=2)
    with pytest.raises(ConfigurationError):
        freeze_object([1])
    nested: object = 0
    for _ in range(34):
        nested = [nested]
    with pytest.raises(ConfigurationError):
        freeze_json(nested)


def test_aware_timestamps_and_session_guards() -> None:
    assert timestamp(datetime(2026, 1, 1, tzinfo=timezone.utc)) == 1767225600
    assert timestamp(123.0) == 123
    for invalid in [datetime(2026, 1, 1), float("inf"), True]:
        with pytest.raises(ConfigurationError):
            timestamp(invalid)
    session = SessionSnapshot("s", 123)
    assert session.guard.session_id == "s"
    assert session.guard.revision == 1
    with pytest.raises(ConfigurationError):
        SessionSnapshot("", 123)


def test_snapshot_guards_frozen_params_and_components() -> None:
    activity = make_activity()
    assert activity.guard.activity_id == "activity"
    assert activity.guard.activity_revision == 1
    with pytest.raises(FrozenInstanceError):
        activity.activity_revision = 9
    key = IdleConversationKey("bot", 1, 2, 2)
    record = RuntimeSnapshot(key, SessionSnapshot("s", 200), components={"x": [1]})
    assert record.version == record.store_version == 1
    assert thaw_json(record.components) == {"x": [1]}
    op = PendingOperation("op", "resume", effects={"business": "confirmed"})
    assert op.effects["business"] == "confirmed"
    with pytest.raises(ConfigurationError):
        ActivitySnapshot("s", "a", "", 1, "p", "a", {}, 1, 1, 2)
    with pytest.raises(ConfigurationError):
        ActivitySnapshot("s", "a", "x", 0, "p", "a", {}, 1, 1, 2)


def test_adapter_dispositions_are_validated_and_context_dependencies_detached() -> None:
    assert ActionReceipt().disposition == "rearm"
    spec = ActivitySpec("form", "p", "a", {"x": [1]})
    assert ActionReceipt(disposition="replacement", replacement=spec).replacement == spec
    for arguments in [
        {"disposition": "unknown"},
        {"disposition": "replacement"},
        {"replacement": spec},
    ]:
        with pytest.raises(ConfigurationError):
            ActionReceipt(**arguments)
    dependencies = {"service": object()}
    context = FlowContext(
        IdleConversationKey("bot", 1, 2, 2), make_activity(), "op", 1, dependencies=dependencies
    )
    dependencies["other"] = object()
    assert "other" not in context.dependencies


def test_policies_are_explicit_immutable_and_have_stable_digests() -> None:
    policies = IdlePolicies(
        {"skip": ExemptPolicy(), "p": PromptPolicy(), "q": QuietRestorePolicy()}
    )
    assert len(policies) == 3
    assert list(policies) == ["skip", "p", "q"]
    assert isinstance(policies["p"], PromptPolicy)
    assert policies.digest == IdlePolicies(dict(policies)).digest
    assert policy_digest(PromptPolicy()) != policy_digest(PromptPolicy(after_seconds=1))
    with pytest.raises(ConfigurationError):
        policies["missing"]
    with pytest.raises(ConfigurationError):
        IdlePolicies({})
    with pytest.raises(ConfigurationError):
        IdlePolicies({"": ExemptPolicy()})
    for invalid in [0, -1, float("nan"), True]:
        with pytest.raises(ConfigurationError):
            PromptPolicy(after_seconds=invalid)
    with pytest.raises(ConfigurationError):
        PromptPolicy(controls="bad")
    with pytest.raises(ConfigurationError):
        QuietRestorePolicy(after_seconds=0)


def test_configuration_defaults_and_validation() -> None:
    config = IdleConfig()
    assert not config.enabled
    assert config.max_conversations == 10000
    assert config.ambiguous_send is AmbiguousSendPolicy.SUPPRESS
    invalid_settings = [
        {"poll_seconds": 0},
        {"poll_seconds": float("nan")},
        {"concurrency": 1.5},
        {"claim_limit": 9},
        {"renew_seconds": 30},
        {"lock_wait_seconds": 60},
        {"enabled": 1},
        {"ambiguous_send": "bad"},
        {"poll_seconds": "bad"},
    ]
    for settings in invalid_settings:
        with pytest.raises(ConfigurationError):
            IdleConfig(**settings)


def test_pure_reducer_selects_legal_phases() -> None:
    assert reduce_phase(Phase.DISARMED, Trigger.ENTER) is Phase.ACTIVE
    assert reduce_phase(Phase.ACTIVE, Trigger.DUE_PROMPT) is Phase.PROMPT_PENDING
    assert reduce_phase(Phase.ACTIVE, Trigger.DUE_RESTORE) is Phase.RESTORING
    assert reduce_phase(Phase.PROMPT_PENDING, Trigger.SHOWN) is Phase.PROMPTED
    assert reduce_phase(Phase.PROMPTED, Trigger.CONTINUE) is Phase.RESUMING
    assert reduce_phase(Phase.PROMPTED, Trigger.TIMEOUT) is Phase.ABANDONING
    assert reduce_phase(Phase.RESUMING, Trigger.FINISH) is Phase.ACTIVE
    assert reduce_phase(Phase.RESTORING, Trigger.FINISH) is Phase.DISARMED
    assert reduce_phase(Phase.ACTIVE, Trigger.EXHAUSTED) is Phase.QUARANTINED
    assert reduce_phase(Phase.RESUMING, Trigger.UNKNOWN_EFFECT) is Phase.EFFECT_UNKNOWN
    assert reduce_phase(Phase.PROMPTED, Trigger.CLEAR) is Phase.DISARMED
    assert reduce_phase(Phase.PROMPTED, Trigger.TOUCH) is Phase.ACTIVE
    with pytest.raises(ActivityConflict):
        reduce_phase(Phase.ACTIVE, Trigger.SHOWN)


async def test_manual_clock_wakes_tasks_and_removes_cancelled_waiters() -> None:
    clock = ManualClock(100)
    waiting = asyncio.create_task(clock.sleep(5))
    await asyncio.sleep(0)
    clock.advance(4)
    assert not waiting.done()
    clock.advance(1)
    await waiting
    assert clock.now() == 105
    assert clock.monotonic() == 5
    cancelled = asyncio.create_task(clock.sleep(10))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    clock.advance(20)
    await clock.sleep(0)
    with pytest.raises(ValueError):
        clock.advance(-1)
    with pytest.raises(ValueError):
        ManualClock(float("inf"))
    system = SystemClock()
    assert system.now() > 0
    assert system.monotonic() > 0
    await system.sleep(0)


def test_prompt_receipt_detaches_caller_messages_and_config_update_validates():
    from aiogram_idle.models import ConfigUpdate, MessageRef
    from aiogram_idle.presentation import PromptReceipt

    source = [MessageRef(2, 1)]
    receipt = PromptReceipt("p", messages=source)
    source.clear()
    assert receipt.messages == (MessageRef(2, 1),)
    with pytest.raises(ConfigurationError):
        ConfigUpdate(enabled=1, operation_id="config")
    with pytest.raises(ConfigurationError):
        ConfigUpdate(enabled=True, operation_id="")
