"""Application authority is read-only, live and independent of navigation."""

from dataclasses import replace

import pytest
from aiogram_coordination import ExternalSession

from aiogram_idle import (
    ActivityRegistration,
    ConfigurationError,
    IdleConfig,
    IdleConversationKey,
    IdlePolicies,
    IdleRuntime,
    MemoryIdleBackend,
    Phase,
    PromptPolicy,
    SessionAuthorityUnavailable,
)
from aiogram_idle.clock import ManualClock
from aiogram_idle.controls import ControlContext
from aiogram_idle.errors import ActivityConflict
from aiogram_idle.storage.session_bindings import EXTERNAL_SESSION
from tests.runtime_helpers import Adapter, Presenter

KEY = IdleConversationKey("test", 123456, 42, 42)
FLOW = ActivityRegistration("feedback.typing", "prompt", "form", {"draft_id": "draft"})


class Authority:
    def __init__(self):
        self.value = ExternalSession("application-session", "1", 4_000_000, 3_000_000)
        self.error = None
        self.calls = []

    async def current(self, key):
        self.calls.append(key)
        if self.error:
            raise self.error
        return self.value


async def build(*, activated=True):
    clock = ManualClock(1000)
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(enabled=True))
    authority, adapter, presenter = Authority(), Adapter(), Presenter(clock)
    runtime = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"prompt": PromptPolicy(10, 20)}),
        adapters={"form": adapter},
        presenter=presenter,
        namespace="test",
        session_authority=authority,
    )
    await runtime.initialize()
    if activated:
        await backend.activate_storage_format(
            operation_id="activate-format", old_workers_drained=True, dry_run=False
        )
    return runtime, backend, authority, adapter, presenter, clock


async def test_external_activation_projects_but_never_creates_application_session():
    runtime, backend, authority, _, _, _ = await build()
    original = authority.value
    context = runtime.for_conversation(KEY)
    with pytest.raises(ConfigurationError, match="owned"):
        await context.open_session(operation_id="forbidden", lifetime_seconds=3600)
    activity = await context.activate(FLOW, operation_id="enter")
    assert activity.session_id != original.session_id
    assert activity.expires_at == 4000
    record = await backend.load(KEY)
    assert record.components[EXTERNAL_SESSION]["session_id"] == original.session_id
    assert authority.value is original
    assert (await context.activate(FLOW, operation_id="enter")) == activity


async def test_external_mode_requires_explicit_activation():
    runtime, _, _, _, _, _ = await build(activated=False)
    with pytest.raises(ConfigurationError, match="format 2"):
        await runtime.for_conversation(KEY).activate(FLOW, operation_id="enter")


async def test_expiry_disarms_without_touching_application_draft_or_rendering():
    runtime, backend, authority, adapter, presenter, clock = await build()
    await runtime.for_conversation(KEY).activate(FLOW, operation_id="enter")
    authority.value = None
    clock.advance(10)
    await runtime.run_once()
    record = await backend.load(KEY)
    assert record.idle.phase is Phase.DISARMED
    assert record.activity.params["draft_id"] == "draft"
    assert adapter.calls == [] and presenter.questions == [] and presenter.finishes == []


async def test_authority_outage_is_not_logout_or_abandonment():
    runtime, backend, authority, adapter, presenter, clock = await build()
    activity = await runtime.for_conversation(KEY).activate(FLOW, operation_id="enter")
    authority.error = TimeoutError("session service unavailable")
    with pytest.raises(SessionAuthorityUnavailable):
        await runtime.for_conversation(KEY).touch(expected=activity.guard, operation_id="touch")
    clock.advance(10)
    await runtime.run_once()
    record = await backend.load(KEY)
    assert record.activity.guard == activity.guard
    assert record.idle.phase is Phase.ACTIVE
    assert adapter.calls == [] and presenter.questions == []


async def test_changed_application_session_rejects_old_prompt_answer():
    runtime, backend, authority, adapter, presenter, clock = await build()
    await runtime.for_conversation(KEY).activate(FLOW, operation_id="enter")
    clock.advance(10)
    await runtime.run_once()
    prompt = await runtime.current_prompt(KEY)
    authority.value = replace(authority.value, session_id="new-session")
    answer = await runtime.continue_current(
        ControlContext(
            key=KEY,
            actor_id=42,
            transport="commands",
            prompt_id=prompt.prompt_id,
            operation_id="answer",
        )
    )
    assert not answer.accepted and answer.outcome == "expired"
    assert "resume" not in adapter.calls and presenter.finishes == []
    assert (await backend.load(KEY)).idle.phase is Phase.DISARMED


async def test_absolute_expiry_cannot_change_under_same_application_id():
    runtime, _, authority, _, _, _ = await build()
    context = runtime.for_conversation(KEY)
    await context.activate(FLOW, operation_id="enter")
    authority.value = replace(authority.value, absolute_expires_at=5_000_000)
    with pytest.raises(ActivityConflict, match="absolute"):
        await context.activate(FLOW, operation_id="changed")


async def test_insufficient_remaining_application_lifetime_does_not_ask():
    runtime, _, authority, _, presenter, clock = await build()
    await runtime.for_conversation(KEY).activate(FLOW, operation_id="enter")
    authority.value = replace(authority.value, idle_expires_at=1_020_000)
    clock.advance(10)
    await runtime.run_once()
    assert presenter.questions == []


async def test_projection_does_not_replace_unresolved_effect_evidence():
    runtime, backend, authority, _, _, _ = await build()
    await runtime.for_conversation(KEY).activate(FLOW, operation_id="enter")
    from aiogram_idle.models import PendingOperation

    record = await backend.load(KEY)
    operation = PendingOperation("unknown-send", "prompt", effects={"question": "started"})
    await backend.transition(
        KEY,
        expected_version=record.store_version,
        operation_id="uncertain",
        fingerprint="uncertain",
        transform=lambda old: replace(
            old, idle=replace(old.idle, phase=Phase.DELIVERY_UNKNOWN, operation=operation)
        ),
    )
    authority.value = replace(authority.value, session_id="new-session")
    with pytest.raises(ActivityConflict, match="operation"):
        await runtime.for_conversation(KEY).activate(FLOW, operation_id="new")
    assert (await backend.load(KEY)).idle.operation == operation


async def test_registration_is_defensively_copied_and_owned_mode_works():
    params = {"draft_id": "draft"}
    registration = ActivityRegistration("form", "prompt", "form", params)
    params["draft_id"] = "changed"
    assert registration.params["draft_id"] == "draft"
    runtime, _, _, _, _, _ = await build()
    runtime = IdleRuntime(
        backend=runtime.backend,
        policies=runtime.policies,
        adapters=runtime.adapters,
        presenter=runtime.presenter,
        namespace="test",
    )
    context = runtime.for_conversation(KEY)
    await context.open_session(operation_id="session", lifetime_seconds=100)
    result = await context.activate(registration, operation_id="enter")
    assert result.params["draft_id"] == "draft"
