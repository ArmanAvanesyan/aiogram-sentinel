"""The component host commits one canonical ledger without a second receipt."""

import json
from dataclasses import replace

import pytest

from aiogram_idle import IdleConfig, IdleConversationKey, MemoryIdleBackend
from aiogram_idle.clock import ManualClock
from aiogram_idle.errors import ConfigurationError, VersionConflict
from aiogram_idle.models import RuntimeSnapshot, SessionSnapshot

KEY = IdleConversationKey("canonical", 1, 42, 42)
COMPONENT = "example"
IDENTITY = "full-opaque-peer-identity"


def hot(revision, pending=None):
    return json.dumps(
        {
            "schema_version": 3,
            "kind": "hot",
            "revision": revision,
            "pending_id": pending,
            "current_owner": None,
            "core": {},
        },
        sort_keys=True,
    )


def row(operation_id, status):
    return json.dumps(
        {
            "schema_version": 3,
            "kind": "operation",
            "id": operation_id,
            "status": status,
            "conversation": IDENTITY,
            "core": {},
            "integration_payload": None,
        },
        sort_keys=True,
    )


def delta(before, after, *, put=None, delete=(), duration=None, indexes=None, index_delete=()):
    return {
        "expected_revision": before,
        "revision": after,
        "hot": hot(after),
        "put": put or {},
        "delete": list(delete),
        "terminal_retention_ms": duration or {},
        "token_index_put": indexes or {},
        "token_index_delete": list(index_delete),
    }


def record(previous, revision):
    session = previous.session if previous else SessionSnapshot("session", 2000)
    components = {
        COMPONENT: {
            "canonical": True,
            "revision": revision,
            "hot": hot(revision),
            "identity": IDENTITY,
        },
        "__idle_owner__": {"component": COMPONENT, "pending": False, "retain_until": 2000},
    }
    return (
        replace(previous, components=components)
        if previous
        else RuntimeSnapshot(KEY, session, components=components)
    )


async def setup():
    backend = MemoryIdleBackend(clock=ManualClock(1000), config=IdleConfig())
    for expected in [1, 2]:
        await backend.activate_storage_format(
            expected=expected,
            target=expected + 1,
            operation_id=str(expected),
            old_workers_drained=True,
            dry_run=False,
        )
    return backend


async def write(backend, previous, payload):
    return await backend.canonical_component_transaction(
        KEY,
        component=COMPONENT,
        expected_version=previous.store_version if previous else None,
        record=record(previous, payload["revision"]),
        ledger_delta=payload,
    )


async def test_canonical_memory_no_generic_snapshot_or_ack_receipts():
    backend = await setup()
    accepted = await write(backend, None, delta(None, "1", put={"one": row("one", "prepared")}))
    assert backend._receipts.items.get(KEY, {}) == {}
    assert accepted.components[COMPONENT]["revision"] == "1"
    read = await backend.canonical_component_read(KEY, component=COMPONENT, operation_id="one")
    assert read["operations"] == {"one": row("one", "prepared")}
    assert read["retained_count"] == 1


async def test_terminal_rewrite_preserves_commit_expiry_and_maximum_index_field():
    backend = await setup()
    name = "x" * 256
    accepted = await write(
        backend,
        None,
        delta(
            None,
            "1",
            put={name: row(name, "completed")},
            duration={name: 1000},
            indexes={"o:" + name: name},
        ),
    )
    backend.clock.advance(0.5)
    accepted = await write(backend, accepted, delta("1", "2", put={name: row(name, "completed")}))
    read = await backend.canonical_component_read(KEY, component=COMPONENT, operation_id=name)
    assert read["operation_expiry"][name] == 1001000
    backend.clock.advance(0.6)
    accepted = await write(
        backend, accepted, delta("2", "3", delete=[name], index_delete=["o:" + name])
    )
    assert (await backend.canonical_component_read(KEY, component=COMPONENT))["retained_count"] == 0
    assert backend._canonical_rows[(KEY, COMPONENT)].indexes == {}


async def test_failed_hot_guard_preserves_all_canonical_rows():
    backend = await setup()
    await write(backend, None, delta(None, "1", put={"one": row("one", "unknown")}))
    with pytest.raises(VersionConflict):
        await write(backend, None, delta("1", "2", put={"two": row("two", "prepared")}))
    assert set(backend._canonical_rows[(KEY, COMPONENT)].rows) == {"one"}


async def test_pending_never_ttl_and_terminal_requires_first_duration():
    backend = await setup()
    with pytest.raises(ConfigurationError):
        await write(
            backend, None, delta(None, "1", put={"one": row("one", "unknown")}, duration={"one": 1})
        )
    with pytest.raises(ConfigurationError):
        await write(backend, None, delta(None, "1", put={"one": row("one", "completed")}))
    assert await backend.load(KEY) is None


async def test_expired_id_can_be_atomically_replaced_without_early_eviction():
    backend = await setup()
    accepted = await write(
        backend,
        None,
        delta(None, "1", put={"one": row("one", "completed")}, duration={"one": 1000}),
    )
    with pytest.raises(ConfigurationError):
        await write(
            backend, accepted, delta("1", "2", delete=["one"], put={"one": row("one", "prepared")})
        )
    backend.clock.advance(1)
    await write(
        backend, accepted, delta("1", "2", delete=["one"], put={"one": row("one", "prepared")})
    )
    assert backend._canonical_rows[(KEY, COMPONENT)].expiry == {}


def test_explicit_expired_owner_outside_sweep_batch_has_authoritative_proof():
    from aiogram_idle.storage.canonical import CanonicalRows, observe

    names = [f"op{index:02}" for index in range(40)]
    state = CanonicalRows(
        {name: row(name, "completed") for name in names},
        {name: 1000 for name in names},
        {"v:explicit": "op39"},
        set(names),
    )
    result = observe(state, "1", hot("1"), now_ms=2000, index_keys=("v:explicit",))
    assert "op39" in result["expired"]
    assert len(result["expired"]) == 33
    assert result["indexes"] == {"v:explicit": "op39"}
    assert result["operations"] == {}
