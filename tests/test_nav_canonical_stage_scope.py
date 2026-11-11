"""Canonical stage evidence shares task-safe locks across recorder objects."""

import asyncio

import pytest

from aiogram_idle import IdleConfig, MemoryIdleBackend
from aiogram_idle.clock import ManualClock
from aiogram_idle.errors import EffectUnknown, OwnershipLost
from aiogram_idle.integrations.nav.canonical_effects import CanonicalNavigationEffects
from aiogram_idle.integrations.nav.effects import NavigationEffects
from tests.test_nav_runtime import make


async def test_canonical_recorders_serialize_delegated_calls_cancel_and_reject_recursion(
    monkeypatch,
):
    clock = ManualClock(1000)
    backend = MemoryIdleBackend(clock=clock, config=IdleConfig(enabled=True), storage_format=3)
    integration, nav, screens, _, key = make(backend=backend)
    original = screens.render
    calls = []

    async def render(request):
        if not isinstance(request.effects, NavigationEffects):
            return await original(request)
        first = request.effects.effects
        if not isinstance(first, CanonicalNavigationEffects):
            return await original(request)
        second = CanonicalNavigationEffects(first.outer, first.repo, first.key, first.operation_id)

        async def effect():
            calls.append("send")
            await asyncio.sleep(0)
            return "original"

        assert await asyncio.gather(
            first.run("shared", effect, replay_safe=True),
            second.run("shared", effect, replay_safe=True),
        ) == ["original", "original"]
        assert calls == ["send"]

        async def recurse():
            return await second.run("recursive", effect, replay_safe=True)

        with pytest.raises(EffectUnknown, match="recursively"):
            await first.run("recursive", recurse, replay_safe=True)
        await first.checkpoint("recursive", "not_sent")
        assert calls == ["send"]
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocked():
            calls.append("blocked")
            entered.set()
            await release.wait()
            return "blocked-original"

        active = asyncio.create_task(first.run("cancel-wait", blocked, replay_safe=True))
        await entered.wait()
        waiting = asyncio.create_task(second.run("cancel-wait", effect, replay_safe=True))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        release.set()
        assert await active == "blocked-original"
        assert await second.run("cancel-wait", effect, replay_safe=True) == "blocked-original"
        assert calls == ["send", "blocked"]
        await first.checkpoint("uncertain", "started")
        await first.checkpoint("uncertain", "unknown")
        with pytest.raises(EffectUnknown):
            await second.run("uncertain", effect)
        assert await first.run("uncertain", effect, replay_safe=True) == "original"
        from aiogram_idle.storage.state import Claim

        original_claim = first.outer.claim
        original_validation = backend.validate_claim

        async def revoked_claim(_):
            raise OwnershipLost("deadline claim revoked")

        first.outer.claim = Claim(first.outer.key, "revoked", 1, clock.now() - 1, clock.now())
        monkeypatch.setattr(backend, "validate_claim", revoked_claim)
        with pytest.raises(OwnershipLost, match="deadline claim revoked"):
            await first.run("claim-revoked", effect, replay_safe=True)
        first.outer.claim = original_claim
        monkeypatch.setattr(backend, "validate_claim", original_validation)
        second._scope = None
        with pytest.raises(OwnershipLost):
            await second.run("revoked", effect, replay_safe=True)
        assert calls == ["send", "blocked", "send"]
        return await original(request)

    screens.render = render
    await nav.for_conversation(key).go("form", operation_id="enter")
    clock.advance(10)
    await integration.idle.run_once()
    from aiogram_idle.controls import ControlContext

    idle_key = integration.navigation_repository.mapping.to_idle(key)
    prompt = await integration.idle.current_prompt(idle_key)
    answer = await integration.idle.continue_current(
        ControlContext(idle_key, 42, prompt_id=prompt.prompt_id, operation_id="continue")
    )
    assert answer.accepted
    assert calls == ["send", "blocked", "send"]
