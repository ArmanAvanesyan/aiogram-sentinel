"""Process death and transaction uncertainty in the optional projection."""

import asyncio
import subprocess
import sys
from uuid import uuid4

import pytest

pytest.importorskip("aiogram_nav")

from aiogram_nav import (
    CleanupResult,
    ConversationKey,
    MessageRef,
    Navigation,
    NavigationRegistry,
    Node,
    RenderResult,
)

from aiogram_idle.config import IdleConfig
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_idle.models import Phase
from aiogram_idle.policies import ExemptPolicy, IdlePolicies, PromptPolicy
from aiogram_idle.runtime import IdleRuntime
from aiogram_idle.storage.redis import RedisIdleBackend
from tests.runtime_helpers import Adapter, Presenter

KEY = ConversationKey("default", 123456, 42, 42)


class Screen:
    replay_safe = True
    calls = 0

    async def render(self, request):
        self.calls += 1
        return RenderResult(request.view_id, (MessageRef(42, 901),))

    async def cleanup(self, request):
        return CleanupResult()


def build(backend):
    idle = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"none": ExemptPolicy(), "draft": PromptPolicy(20, 20)}),
        adapters={"business": Adapter()},
        presenter=Presenter(backend.clock),
    )
    registry = NavigationRegistry(
        roots={"main"},
        nodes=[Node("main", renderer="screen"), Node("editor", parent="main", renderer="screen")],
    )
    integration = NavigationIntegration(
        idle=idle,
        registry=registry,
        policies=NodePolicies(default="none", overrides={"editor": "draft"}),
    )
    presenter = Screen()
    nav = Navigation(
        registry=registry, repository=integration.navigation_repository, presenter=presenter
    )
    integration.bind(nav)
    return idle, integration, nav, presenter


async def test_process_exit_after_confirmed_render_recovers_atomic_activity(
    redis_client, redis_url
):
    prefix = f"combined-process:{uuid4().hex}"
    script = """
import asyncio, os, sys
from aiogram_idle.storage.redis import RedisIdleBackend
from aiogram_idle.config import IdleConfig
from aiogram_nav import EffectCheckpoint, RenderResult, MessageRef
from tests.test_nav_atomic_recovery import build, KEY
async def main():
    backend = RedisIdleBackend.from_url(sys.argv[1], prefix=sys.argv[2], config=IdleConfig(enabled=True))
    await backend.initialize()
    idle, integration, nav, presenter = build(backend)
    prepared = await nav.for_conversation(KEY).prepare_render("editor", params={"draft_id":"draft"}, operation_id="crashed")
    repo = integration.navigation_repository
    await repo.checkpoint(KEY, operation_id="crashed", effect=EffectCheckpoint("render", "started"))
    await repo.checkpoint(KEY, operation_id="crashed", effect=EffectCheckpoint("render", "confirmed", RenderResult(prepared.view_id, (MessageRef(42,901),))))
    os._exit(24)
asyncio.run(main())
"""
    process = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", script, redis_url, prefix],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 24, process.stderr
    backend = RedisIdleBackend(redis=redis_client, prefix=prefix, config=IdleConfig(enabled=True))
    await backend.initialize()
    idle, integration, nav, presenter = build(backend)
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    pending = await backend.load(mapped)
    assert pending.activity is None and pending.components["__idle_owner__"]["pending"]
    # Make the generic recovery deadline eligible without real-time sleeping.
    from dataclasses import replace

    from aiogram_idle.models import freeze_object

    owner = dict(pending.components["__idle_owner__"])
    owner["recovery_at"] = backend.clock.now()
    changed = replace(
        pending,
        components=freeze_object(
            {**pending.components, "__idle_owner__": owner}, max_bytes=8_388_608
        ),
    )
    await backend.component_transaction(
        mapped,
        component="aiogram_nav",
        expected_version=pending.version,
        operation_id="make-recovery-due",
        fingerprint="make-recovery-due",
        record=changed,
    )
    await idle.run_once()
    result = await backend.load(mapped)
    current = await nav.for_conversation(KEY).current()
    assert current is not None and result.activity is not None
    assert current.session_id == result.activity.session_id == result.session.session_id
    assert current.activity_revision == result.activity.activity_revision
    assert result.idle.phase == Phase.ACTIVE and result.idle.deadline is not None
    assert not result.components["__idle_owner__"]["pending"]
    assert presenter.calls == 0  # Recovery reused the confirmed render.


from tests.test_nav_matrix import combined_backend as _combined_backend  # noqa: E402

combined_backend = _combined_backend


async def test_unknown_component_delivery_is_parked_without_automatic_resend(combined_backend):
    backend = combined_backend
    idle, integration, nav, presenter = build(backend)
    presenter.replay_safe = False

    async def uncertain(request):
        presenter.calls += 1
        raise ConnectionError("The Telegram response was lost")

    presenter.render = uncertain
    from aiogram_nav import RenderUnknown

    with pytest.raises(RenderUnknown):
        await nav.for_conversation(KEY).go("editor", operation_id="uncertain")
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    record = await backend.load(mapped)
    from dataclasses import replace

    from aiogram_idle.models import freeze_object

    owner = dict(record.components["__idle_owner__"])
    owner["recovery_at"] = backend.clock.now()
    await backend.component_transaction(
        mapped,
        component="aiogram_nav",
        expected_version=record.version,
        operation_id="unknown-due",
        fingerprint="unknown-due",
        record=replace(
            record,
            components=freeze_object(
                {**record.components, "__idle_owner__": owner}, max_bytes=8_388_608
            ),
        ),
    )
    await idle.run_once()
    parked = await backend.load(mapped)
    assert parked.components["__idle_owner__"]["parked"]
    assert parked.components["__idle_owner__"]["pending"]
    assert presenter.calls == 1 and not idle.presenter.questions
    assert not await backend.claim_due(limit=1, lease_seconds=10)
    await idle.run_once()
    assert presenter.calls == 1


async def test_old_prompt_cannot_reserve_an_answer_during_pending_navigation(combined_backend):
    backend = combined_backend
    idle, integration, nav, _ = build(backend)
    await nav.for_conversation(KEY).go("editor", operation_id="entry")
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    from dataclasses import replace

    from aiogram_idle.controls import ControlContext

    record = await backend.load(mapped)
    await backend.transition(
        mapped,
        expected_version=record.version,
        operation_id="prompt-due",
        fingerprint="prompt-due",
        transform=lambda old: replace(old, idle=replace(old.idle, deadline=backend.clock.now())),
    )
    await idle.run_once()
    assert (await backend.load(mapped)).idle.phase == Phase.PROMPTED
    prepared = await nav.for_conversation(KEY).prepare_render("main", operation_id="new-view")
    before = await backend.load(mapped)
    answer = await idle.continue_current(ControlContext(mapped, 42, operation_id="old-prompt"))
    assert not answer.accepted and answer.outcome == "busy"
    unchanged = await backend.load(mapped)
    assert unchanged.version == before.version and unchanged.idle.operation is None
    assert (await integration.navigation_repository.pending(KEY)).operation_id == "new-view"
    await nav.complete(prepared, rendered=RenderResult(prepared.view_id, (MessageRef(42, 902),)))
    assert (await backend.load(mapped)).idle.prompt is None
    assert (await nav.for_conversation(KEY).current()).node_id == "main"


async def test_staged_cancel_recovers_failed_final_commit_without_repeating_effects(
    combined_backend, monkeypatch
):
    backend = combined_backend
    idle, integration, nav, presenter = build(backend)
    application = Adapter()
    integration.adapters["editor"] = application
    await nav.for_conversation(KEY).go("editor", params={"draft_id": "draft"}, operation_id="entry")
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    from dataclasses import replace

    from aiogram_idle.controls import ControlContext
    from aiogram_idle.errors import PersistenceUnavailable

    before = await backend.load(mapped)
    old_view = (await nav.for_conversation(KEY).current()).view.view_id
    await backend.transition(
        mapped,
        expected_version=before.version,
        operation_id="cancel-prompt-due",
        fingerprint="cancel-prompt-due",
        transform=lambda old: replace(old, idle=replace(old.idle, deadline=backend.clock.now())),
    )
    await idle.run_once()
    original = backend.transition
    failed = False

    async def fail_final_once(*args, **kwargs):
        nonlocal failed
        if not failed and kwargs["fingerprint"].endswith(":complete"):
            failed = True
            raise PersistenceUnavailable("Completion was not available")
        return await original(*args, **kwargs)

    monkeypatch.setattr(backend, "transition", fail_final_once)
    answer = await idle.cancel_current(ControlContext(mapped, 42, operation_id="cancel"))
    assert answer.accepted and failed
    staged = await backend.load(mapped)
    assert staged.idle.operation is not None
    assert (await nav.for_conversation(KEY).current()).view.view_id == old_view
    assert staged.activity == before.activity
    calls = presenter.calls
    assert application.calls.count("abandon:cancelled") == 1
    await original(
        mapped,
        expected_version=staged.version,
        operation_id="retry-staged",
        fingerprint="retry-staged",
        transform=lambda old: replace(old, idle=replace(old.idle, deadline=backend.clock.now())),
    )
    await idle.run_once()
    finished = await backend.load(mapped)
    current = await nav.for_conversation(KEY).current()
    assert finished.idle.operation is None and finished.idle.phase == Phase.DISARMED
    assert current.node_id == "main" and current.view.view_id != old_view
    assert finished.activity.activity_key == "main"
    assert finished.activity.activity_revision == current.activity_revision
    assert presenter.calls == calls and application.calls.count("abandon:cancelled") == 1
