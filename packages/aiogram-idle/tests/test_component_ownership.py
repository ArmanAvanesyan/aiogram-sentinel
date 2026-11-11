"""Generic coordinator shutdown ownership remains valid without navigation."""

import asyncio
from uuid import uuid4

import pytest

from aiogram_idle.errors import ConfigurationError, OwnershipLost
from aiogram_idle.models import IdleConversationKey
from aiogram_idle.storage.redis import RedisIdleBackend


async def test_revoked_but_unwinding_handler_blocks_backend_close(redis_client):
    backend = RedisIdleBackend(redis=redis_client, prefix=f"component-drain:{uuid4().hex}")
    coordinator = backend.coordinator
    coordinator.renew_seconds = 0.01
    key = IdleConversationKey("default", 1, 42, 42)
    entered, revoked, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def work():
        async with coordinator.hold(key):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                revoked.set()
                await release.wait()

    task = asyncio.create_task(work())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await redis_client.delete(coordinator.lock_key(key))
        await asyncio.wait_for(revoked.wait(), 5)
        assert coordinator.active_scopes > 0
        with pytest.raises(ConfigurationError):
            await backend.close()
        release.set()
        with pytest.raises(OwnershipLost):
            await asyncio.wait_for(task, 5)
        assert coordinator.active_scopes == 0
        await backend.close()
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
