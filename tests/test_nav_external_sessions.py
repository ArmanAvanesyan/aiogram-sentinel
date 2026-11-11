"""Application session bindings participate in the same navigation/activity commit."""

from dataclasses import replace

import pytest

pytest.importorskip("aiogram_nav")
from aiogram_nav.errors import SessionExpired

from aiogram_idle import Phase
from aiogram_idle.controls import ControlContext
from aiogram_idle.storage.session_bindings import EXTERNAL_SESSION
from tests.test_external_sessions import Authority
from tests.test_nav_runtime import make


async def external():
    authority = Authority()
    integration, nav, screens, clock, key = make(session_authority=authority)
    await integration.idle.initialize()
    if await integration.idle.backend.storage_format() < 2:
        await integration.idle.backend.activate_storage_format(
            operation_id="activate", old_workers_drained=True, dry_run=False
        )
    return integration, nav, screens, clock, key, authority


async def test_external_navigation_activity_share_binding_and_absolute_expiry():
    integration, nav, _, _, key, authority = await external()
    await nav.for_conversation(key).go("form", params={"draft_id": "draft"}, operation_id="enter")
    record = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    current = await nav.for_conversation(key).current()
    assert record.session.session_id == record.activity.session_id == current.session_id
    assert current.expires_at == authority.value.absolute_expires_at
    assert record.session.expires_at * 1000 == current.expires_at
    assert record.components[EXTERNAL_SESSION]["session_id"] == authority.value.session_id
    assert record.activity.activity_revision == current.activity_revision


async def test_external_prompt_continue_remains_atomic():
    integration, nav, _, clock, key, authority = await external()
    await nav.for_conversation(key).go("form", params={"draft_id": "draft"}, operation_id="enter")
    idle_key = integration.navigation_repository.mapping.to_idle(key)
    clock.advance(10)
    await integration.idle.run_once()
    assert (await integration.idle.inspect(idle_key)).idle.phase is Phase.PROMPTED
    prompt = await integration.idle.current_prompt(idle_key)
    answer = await integration.idle.continue_current(
        ControlContext(idle_key, 42, prompt_id=prompt.prompt_id, operation_id="answer")
    )
    assert answer.accepted
    record = await integration.idle.inspect(idle_key)
    current = await nav.for_conversation(key).current()
    assert record.activity.activity_revision == current.activity_revision
    assert record.session.session_id == current.session_id
    assert current.expires_at == authority.value.absolute_expires_at


async def test_old_external_generation_cannot_resume_after_session_change():
    integration, nav, screens, _, key, authority = await external()
    await nav.for_conversation(key).go("form", params={"draft_id": "draft"}, operation_id="enter")
    old = await nav.for_conversation(key).current()
    authority.value = replace(authority.value, session_id="new-application-session")
    with pytest.raises(SessionExpired):
        await nav.authorize_session(key, old.session_id)
    assert screens.renders == ["form"]
    await nav.for_conversation(key).go("main", operation_id="new-session")
    current = await nav.for_conversation(key).current()
    assert current.session_id != old.session_id
    assert current.node_id == "main"
