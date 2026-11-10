"""Integrated navigation generation and retained-evidence patch regressions."""

from uuid import uuid4

import pytest

pytest.importorskip("aiogram_nav")
from aiogram_idle import IdleConfig
from aiogram_idle.storage.redis import RedisIdleBackend
from tests.test_nav_runtime import make


async def test_first_prepared_abandon_preserves_generation_and_expiry():
    integration, nav, _, _, key = make()
    context = nav.for_conversation(key)
    prepared = await context.prepare_action("go", node_id="main", operation_id="first")
    before = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    await integration.navigation_repository.abandon(
        key, prepared.operation_id, expected_session_id=prepared.session_id
    )
    after = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    assert after.session == before.session
    assert after.session.session_id == prepared.session_id
    assert await context.current() is None
    next_action = await context.prepare_action("go", node_id="main", operation_id="next")
    assert next_action.session_id == prepared.session_id
    assert next_action.expires_at == prepared.expires_at
    from aiogram_nav import MessageRef, RenderResult

    await context.complete_render(
        next_action, rendered=RenderResult(next_action.view_id, (MessageRef(42, 5),))
    )
    assert (await context.current()).session_id == prepared.session_id
    final = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    assert final.session == before.session


async def test_redis_first_abandon_preserves_session_and_rejects_wrong_generation(redis_client):
    from aiogram_nav.errors import SessionExpired

    backend = RedisIdleBackend(
        redis=redis_client,
        prefix="test:021:abandon:" + uuid4().hex,
        config=IdleConfig(enabled=True),
    )
    await backend.initialize()
    integration, nav, _, _, key = make(backend=backend)
    context = nav.for_conversation(key)
    prepared = await context.prepare_action("go", node_id="main", operation_id="first")
    with pytest.raises(SessionExpired):
        await integration.navigation_repository.abandon(
            key, prepared.operation_id, expected_session_id="foreign"
        )
    before = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    await integration.navigation_repository.abandon(
        key, prepared.operation_id, expected_session_id=prepared.session_id
    )
    after = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    assert after.session == before.session
    subsequent = await context.prepare_action("go", node_id="main", operation_id="second")
    assert subsequent.session_id == prepared.session_id
    assert subsequent.expires_at == prepared.expires_at


async def test_unknown_render_evidence_survives_explicit_abandon():
    from aiogram_nav.models import EffectCheckpoint

    integration, nav, _, _, key = make()
    prepared = await nav.for_conversation(key).prepare_action(
        "go", node_id="main", operation_id="uncertain"
    )
    repository = integration.navigation_repository
    await repository.checkpoint(
        key, operation_id=prepared.operation_id, effect=EffectCheckpoint("render", "unknown")
    )
    await repository.mark_unknown(key, operation_id=prepared.operation_id)
    before = await repository.lookup_operation(key, operation_id=prepared.operation_id)
    await repository.abandon(key, prepared.operation_id, expected_session_id=prepared.session_id)
    after = await repository.lookup_operation(key, operation_id=prepared.operation_id)
    assert after.status == "failed"  # explicit application abandonment, no resend
    assert after.prepared.effects == before.prepared.effects
    assert after.prepared.effects["render"].state == "unknown"


async def test_expired_prepared_generation_cannot_complete_or_extend_session():
    from aiogram_nav import MessageRef, RenderResult
    from aiogram_nav.errors import SessionExpired

    integration, nav, _, _, key = make()
    context = nav.for_conversation(key)
    prepared = await context.prepare_action("go", node_id="main", operation_id="expired")
    before = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    integration.idle.clock.advance(prepared.expires_at / 1000 - integration.idle.clock.now() + 1)
    with pytest.raises(SessionExpired):
        await context.complete_render(
            prepared, rendered=RenderResult(prepared.view_id, (MessageRef(42, 1),))
        )
    after = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    assert after.session == before.session
