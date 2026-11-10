"""Whole-task isolation and borrowed effect-capability lifetime."""

import asyncio

from aiogram_coordination import MemoryCoordinator


async def test_nested_ownership_does_not_leak_to_child_or_other_key():
    coordinator = MemoryCoordinator()
    async with coordinator.hold("one"):
        token = coordinator.scope_token("one")
        assert coordinator.scope_active(token) and coordinator.lock_count == 1
        async with coordinator.hold("one"):
            assert coordinator.scope_token("one") is token

        async def child():
            assert not coordinator.owns("one")
            assert coordinator.scope_matches("one", token)
            assert not coordinator.scope_matches("two", token)
            async with coordinator.hold("two"):
                assert coordinator.active_scopes == 2

        await asyncio.create_task(child())
    assert not coordinator.scope_active(token)
    assert coordinator.active_scopes == coordinator.lock_count == 0


async def test_same_key_waits_but_different_key_can_enter():
    coordinator = MemoryCoordinator()
    pending = asyncio.Event()
    entered = asyncio.Event()

    async def waiter():
        pending.set()
        async with coordinator.hold("one"):
            entered.set()

    async with coordinator.hold("one"):
        task = asyncio.create_task(waiter())
        await pending.wait()
        async with coordinator.hold("two"):
            assert not entered.is_set()
    await task
    assert entered.is_set() and coordinator.lock_count == 0


async def test_cancelled_waiter_does_not_leak_lock_entry():
    coordinator = MemoryCoordinator()
    ready = asyncio.Event()

    async def waiter():
        ready.set()
        async with coordinator.hold("one"):
            raise AssertionError("waiter acquired")

    async with coordinator.hold("one"):
        task = asyncio.create_task(waiter())
        await ready.wait()
        task.cancel()
        import pytest

        with pytest.raises(asyncio.CancelledError):
            await task
        assert coordinator.active_scopes == 1
    assert coordinator.lock_count == 0


async def test_structural_peer_identity_shares_one_task_scope():
    from dataclasses import dataclass

    from aiogram_coordination import CoordinationKey

    @dataclass(frozen=True)
    class PeerKey:
        namespace: str
        bot_id: int
        chat_id: int
        user_id: int
        tenant_id: str | None = None

    coordinator = MemoryCoordinator()
    original = CoordinationKey("project", 1, 2, 2, "tenant")
    peer = PeerKey("project", 1, 2, 2, "tenant")
    async with coordinator.hold(original):
        scope = coordinator.scope_token(original)
        async with coordinator.hold(peer):
            assert coordinator.scope_token(peer) is scope
            assert coordinator.scope_matches(peer, scope)
            assert coordinator.active_scopes == 1
