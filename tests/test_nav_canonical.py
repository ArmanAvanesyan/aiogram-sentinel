"""Canonical combined mode retains one Nav operation plus its original activity."""

from aiogram_nav import MessageRef, RenderResult

from aiogram_idle import IdleConfig, MemoryIdleBackend
from aiogram_idle.clock import ManualClock
from tests.test_nav_runtime import make


async def test_memory_canonical_framework_go_and_atomic_track():
    backend = MemoryIdleBackend(
        clock=ManualClock(1000), config=IdleConfig(enabled=True), storage_format=3
    )
    integration, nav, screens, _, key = make(backend=backend)
    context = nav.for_conversation(key)
    await context.go("main", operation_id="main")
    assert (await context.current()).node_id == "main"
    for index in range(20):
        accepted = await context.track(
            "form",
            rendered=RenderResult(f"view:{index}", (MessageRef(42, index + 10),)),
            operation_id=f"track:{index}",
            params={"draft_id": "draft"},
        )
        assert accepted.node_id == "form"
    assert len(screens.renders) == 1
    assert (
        backend._receipts.items.get(integration.navigation_repository.mapping.to_idle(key), {})
        == {}
    )
    rows = next(iter(backend._canonical_rows.values()))
    assert len(rows.rows) == 21
    record = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    assert record.components["aiogram_nav"]["canonical"] is True
    assert "activity_receipts" not in record.components["aiogram_nav"]
    assert "ledger" not in record.components["aiogram_nav"]
    assert (await context.current()).node_id == "form"


async def test_canonical_continue_is_one_atomic_activity_and_navigation_commit():
    from aiogram_idle.controls import ControlContext
    from aiogram_idle.models import Phase

    clock = ManualClock(1000)
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(enabled=True), storage_format=3)
    integration, nav, screens, _, key = make(backend=backend)
    await nav.for_conversation(key).go("form", operation_id="start")
    idle_key = integration.navigation_repository.mapping.to_idle(key)
    before = await integration.idle.inspect(idle_key)
    clock.advance(10)
    assert (await integration.idle.run_once()).completed == 1
    prompt = await integration.idle.current_prompt(idle_key)
    result = await integration.idle.continue_current(
        ControlContext(idle_key, 42, prompt_id=prompt.prompt_id, operation_id="continue")
    )
    current = await integration.idle.inspect(idle_key)
    assert result.accepted and current.idle.phase is Phase.ACTIVE
    assert current.idle.operation is None
    assert current.activity.activity_id == before.activity.activity_id
    assert current.activity.activity_revision == before.activity.activity_revision + 1
    assert (
        await nav.for_conversation(key).current()
    ).activity_revision == current.activity.activity_revision
    assert current.idle.deadline == 1010 + 10
    assert len(screens.renders) == 2


async def test_fresh_navigation_uses_existing_idle_absolute_generation_before_prepare():
    clock = ManualClock(1000)
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(enabled=True), storage_format=3)
    integration, nav, _, _, key = make(backend=backend)
    idle_key = integration.navigation_repository.mapping.to_idle(key)
    session = await backend.open_session(idle_key, lifetime_seconds=7200, operation_id="session")
    await nav.for_conversation(key).go("main", operation_id="enter")
    current = await nav.for_conversation(key).current()
    assert current.session_id == session.session_id
    assert current.expires_at == round(session.expires_at * 1000)
    assert (await integration.idle.inspect(idle_key)).session == session
