"""Memory and Redis migration share immutable staged-source semantics."""

from dataclasses import replace

import pytest

from aiogram_idle import IdleConfig, MemoryIdleBackend
from aiogram_idle.clock import ManualClock
from aiogram_idle.errors import VersionConflict
from aiogram_idle.models import RuntimeSnapshot, SessionSnapshot
from tests.test_canonical_components import COMPONENT, IDENTITY, KEY, delta, hot, row


async def test_bounded_migration_keeps_source_until_verified_cutover():
    backend = MemoryIdleBackend(clock=ManualClock(1000), config=IdleConfig(), storage_format=3)
    source = {"schema": 1, "ledger": "legacy"}
    before = RuntimeSnapshot(KEY, SessionSnapshot("session", 2000), components={COMPONENT: source})
    backend._records[KEY] = before
    target = {"canonical": True, "revision": "1", "hot": hot("1"), "identity": IDENTITY}
    payload = delta(
        None, "1", put={"a": row("a", "completed"), "b": row("b", "prepared")}, duration={"a": 5000}
    )
    args = dict(
        component=COMPONENT,
        source_component=source,
        target_component=target,
        ledger_delta=payload,
        absolute_expiry={"a": 1005000},
        limit=1,
        dry_run=False,
    )
    for index in range(4):
        page = await backend.canonical_component_migrate(KEY, **args)
        assert page.done is (index == 3)
        assert (await backend.load(KEY)).components[COMPONENT] == (target if page.done else source)
    after = await backend.load(KEY)
    assert after.session == before.session and after.activity == before.activity
    assert backend._canonical_rows[(KEY, COMPONENT)].expiry == {"a": 1005000}
    assert (await backend.canonical_component_migrate(KEY, **args)).done


async def test_changed_source_rejects_staged_cutover_without_replacing_it():
    backend = MemoryIdleBackend(clock=ManualClock(1000), storage_format=3)
    source = {"schema": 1, "ledger": "legacy"}
    before = RuntimeSnapshot(KEY, SessionSnapshot("session", 2000), components={COMPONENT: source})
    backend._records[KEY] = before
    target = {"canonical": True, "revision": "1", "hot": hot("1"), "identity": IDENTITY}
    payload = delta(None, "1", put={"a": row("a", "prepared")})
    args = dict(
        component=COMPONENT,
        source_component=source,
        target_component=target,
        ledger_delta=payload,
        absolute_expiry={},
        limit=1,
        dry_run=False,
    )
    await backend.canonical_component_migrate(KEY, **args)
    changed = replace(before, components={COMPONENT: {"ledger": "repaired"}})
    backend._records[KEY] = changed
    with pytest.raises(VersionConflict):
        await backend.canonical_component_migrate(KEY, **args)
    assert await backend.load(KEY) == changed
