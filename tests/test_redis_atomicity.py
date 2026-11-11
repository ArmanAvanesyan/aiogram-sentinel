"""Real-server races at the reduction/commit boundary."""

import asyncio
import hashlib
import json
from uuid import uuid4

import pytest

from aiogram_idle import IdleConversationKey, PromptPolicy
from aiogram_idle.errors import BackendInconsistent, OwnershipLost, SessionExpired
from aiogram_idle.storage.redis import RedisIdleBackend
from aiogram_idle.storage.redis_scripts import COMMIT, LEASE


def sha(source):
    return hashlib.sha1(source.encode(), usedforsecurity=False).hexdigest()


class Intercept:
    def __init__(self, client):
        self.client = client
        self.before_commit = None
        self.lease_commands = []

    async def execute_command(self, *args):
        if args[0] == "EVALSHA" and args[1] == sha(COMMIT) and self.before_commit:
            callback, self.before_commit = self.before_commit, None
            await callback()
        if args[0] == "EVALSHA" and args[1] == sha(LEASE):
            self.lease_commands.append(args)
        return await self.client.execute_command(*args)


async def setup(client):
    backend = RedisIdleBackend(redis=client, prefix=f"test:atomic:{uuid4().hex}")
    await backend.initialize()
    key = IdleConversationKey("test", 1, 42, 42)
    session = await backend.open_session(key, lifetime_seconds=60, operation_id="session")
    activity = await backend.enter(
        key,
        "draft",
        policy_id="draft",
        policy=PromptPolicy(after_seconds=0.01),
        adapter_key="draft",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )
    return backend, key, activity


async def test_stolen_conversation_lock_fences_commit(redis_client):
    client = Intercept(redis_client)
    backend, key, activity = await setup(client)
    async with backend.coordinator.hold(key):
        lock, _ = backend.coordinator.fencing(key)

        async def steal():
            await redis_client.set(lock, "replacement-owner", px=30_000)

        client.before_commit = steal
        with pytest.raises(OwnershipLost):
            await backend.touch(key, expected=activity.guard, operation_id="stolen")
    assert (await backend.load(key)).activity == activity


async def test_expiry_rechecked_at_commit_not_only_python_read(redis_client):
    client = Intercept(redis_client)
    backend = RedisIdleBackend(redis=client, prefix=f"test:atomic:{uuid4().hex}")
    key = IdleConversationKey("test", 1, 42, 42)
    session = await backend.open_session(key, lifetime_seconds=0.3, operation_id="session")
    activity = await backend.enter(
        key,
        "draft",
        policy_id="draft",
        policy=PromptPolicy(),
        adapter_key="draft",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )
    client.before_commit = lambda: asyncio.sleep(0.35)
    with pytest.raises(SessionExpired):
        await backend.touch(key, expected=activity.guard, operation_id="too-late")
    assert (await backend.load(key)).activity == activity
    assert (await backend.lookup_operation(key, "too-late")).status != "found"


async def test_replayed_heartbeat_command_cannot_extend_lease(redis_client):
    client = Intercept(redis_client)
    backend, key, _ = await setup(client)
    await asyncio.sleep(0.02)
    (claim,) = await backend.claim_due(limit=1, lease_seconds=5)
    renewed = await backend.renew_claim(claim, lease_seconds=5)
    command = client.lease_commands[-1]
    await asyncio.sleep(0.03)
    replay = json.loads(await redis_client.execute_command(*command))
    assert replay["lease_until"] == renewed.lease_until
    # An unrelated envelope mutation must preserve this renewal identity too.
    await backend.reserve_control(
        key,
        token="future-inline-token",
        prompt_id="future-prompt",
        activity_id=(await backend.load(key)).activity.activity_id,
        expires_at=backend.clock.now() + 3,
    )
    replay = json.loads(await redis_client.execute_command(*command))
    assert replay["lease_until"] == renewed.lease_until


async def test_wrongtype_commit_fails_before_runtime_write(redis_client):
    client = Intercept(redis_client)
    backend, key, activity = await setup(client)

    async def corrupt():
        await redis_client.delete(backend._store.prefix + ":expiry")
        await redis_client.set(backend._store.prefix + ":expiry", "corruption")

    client.before_commit = corrupt
    with pytest.raises(BackendInconsistent):
        await backend.touch(key, expected=activity.guard, operation_id="wrongtype")
    assert (await backend.load(key)).activity == activity


async def test_namespace_history_loss_fails_closed(redis_client):
    backend, key, _ = await setup(redis_client)
    await redis_client.delete(backend._store.prefix + ":created")
    with pytest.raises(BackendInconsistent):
        await backend.load(key)


def test_server_clock_jump_is_observable(caplog):
    from aiogram_idle.storage.redis_transport import RedisClock

    clock = RedisClock()
    clock.update(1000)
    clock.update(1010)
    assert "Redis clock jumped" in caplog.text
    assert 1010 <= clock.now() < 1011


async def test_new_client_cannot_recreate_missing_namespace_marker(redis_client):
    backend, key, _ = await setup(redis_client)
    await redis_client.delete(backend._store.prefix + ":created")
    other = RedisIdleBackend(redis=redis_client, prefix=backend._store.prefix)
    with pytest.raises(BackendInconsistent):
        await other.initialize()
    assert await redis_client.get(backend._store.keys(key)[0]) is not None


@pytest.mark.parametrize("receipt", [[], {"other": {}}, {"configuration": {"id": True}}])
async def test_malformed_admin_receipt_fails_closed(redis_client, receipt):
    from aiogram_idle.storage.codec import decode, encode

    backend, key, activity = await setup(redis_client)
    await backend.bootstrap_config(enabled=False, policies_digest="digest")
    config_key = backend._store.prefix + ":config"
    value = decode((await redis_client.get(config_key)).decode())
    value["receipts"] = receipt
    await redis_client.set(config_key, encode(value))
    before = await redis_client.get(backend._store.keys(key)[0])
    with pytest.raises(BackendInconsistent):
        await backend.touch(key, expected=activity.guard, operation_id="bad-config")
    assert await redis_client.get(backend._store.keys(key)[0]) == before


async def test_disable_epoch_survives_reenable_without_scan(redis_client, monkeypatch):
    backend = RedisIdleBackend(redis=redis_client, prefix=f"test:atomic:{uuid4().hex}")
    initial = await backend.bootstrap_config(enabled=True, policies_digest="digest")
    key = IdleConversationKey("test", 1, 42, 42)
    session = await backend.open_session(key, lifetime_seconds=60, operation_id="open")
    activity = await backend.enter(
        key,
        "draft",
        policy_id="draft",
        policy=PromptPolicy(after_seconds=0.01),
        adapter_key="draft",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )
    original = await backend.load(key)

    async def skip_reconcile(*, limit=100):
        return 0

    monkeypatch.setattr(backend, "reconcile", skip_reconcile)
    disabled = await backend.apply_config(
        expected_generation=initial.generation,
        enabled=False,
        policies_digest="digest",
        operation_id="disable",
    )
    enabled = await backend.apply_config(
        expected_generation=disabled.generation,
        enabled=True,
        policies_digest="digest",
        operation_id="enable",
    )
    await asyncio.sleep(0.02)
    assert await backend.claim_due(limit=1, lease_seconds=5) == []
    disarmed = await backend.load(key)
    assert disarmed.idle.deadline is None
    assert disarmed.version > original.version
    # Unrelated configuration updates retain this barrier, while successful explicit
    # activity accepts it and rearms under the now-enabled configuration.
    await backend.apply_config(
        expected_generation=enabled.generation,
        enabled=True,
        policies_digest="newdigest",
        operation_id="policy-change",
    )
    await backend.touch(key, expected=activity.guard, operation_id="accepted", enabled=True)
    assert (await backend.load(key)).idle.deadline is not None


async def test_old_admin_duplicate_does_not_roll_back_later_config(redis_client):
    backend = RedisIdleBackend(redis=redis_client, prefix=f"test:atomic:{uuid4().hex}")
    initial = await backend.bootstrap_config(enabled=True, policies_digest="digest")
    disabled = await backend.apply_config(
        expected_generation=initial.generation,
        enabled=False,
        policies_digest="digest",
        operation_id="disable",
    )
    latest = await backend.apply_config(
        expected_generation=disabled.generation,
        enabled=True,
        policies_digest="digest",
        operation_id="enable",
    )
    duplicate = await backend.apply_config(
        expected_generation=initial.generation,
        enabled=False,
        policies_digest="digest",
        operation_id="disable",
    )
    assert duplicate == disabled
    assert await backend.get_config() == latest


async def test_unsupported_conversation_is_parked_without_starving_healthy_job(redis_client):
    backend, key, _ = await setup(redis_client)
    other = IdleConversationKey("test", 1, 43, 43)
    session = await backend.open_session(other, lifetime_seconds=60, operation_id="other-open")
    await backend.enter(
        other,
        "draft",
        policy_id="draft",
        policy=PromptPolicy(after_seconds=0.01),
        adapter_key="draft",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="other-enter",
        enabled=True,
    )
    record_key = backend._store.keys(key)[0]
    original = await redis_client.get(record_key)
    newer = json.loads(original)
    if backend._store.format_version == 3:
        state = json.loads(newer["state"])
        state["schema_version"] = 999
        newer["state"] = json.dumps(state)
    else:
        newer["schema_version"] = 999
    await redis_client.set(record_key, json.dumps(newer))
    await asyncio.sleep(0.02)
    claims = await backend.claim_due(limit=2, lease_seconds=5)
    assert [claim.key for claim in claims] == [other]
    _, parked = await backend.inspect_parked()
    assert parked == {key: "SchemaUnsupported"}
    retained = json.loads(await redis_client.get(record_key))
    if backend._store.format_version == 3:
        retained = json.loads(retained["state"])
    assert retained["schema_version"] == 999
    await backend.reconcile(limit=10)
    assert (
        await redis_client.zscore(backend._store.keys(key)[2], backend._store.member(key)) is None
    )
    from aiogram_idle.errors import SchemaUnsupported

    with pytest.raises(SchemaUnsupported):
        await backend.release_parked(key)
    await redis_client.set(record_key, original)
    await redis_client.srem(backend._store.prefix + ":routes", backend._store.route(key))
    await backend.release_parked(key)
    assert (await backend.inspect_parked())[1] == {}
    assert [claim.key for claim in await backend.claim_due(limit=1, lease_seconds=5)] == [key]


async def test_admission_rotates_past_128_live_claims_to_prunable_terminal(redis_client):
    from dataclasses import replace

    from aiogram_idle import IdleConfig
    from aiogram_idle.storage.codec import decode, encode

    backend = RedisIdleBackend(
        redis=redis_client,
        prefix=f"test:atomic:{uuid4().hex}",
        config=IdleConfig(max_conversations=129, recovery_retention_seconds=0.03),
    )
    protected = []
    for i in range(128):
        key = IdleConversationKey("test", 1, i + 1, i + 1)
        session = await backend.open_session(key, lifetime_seconds=60, operation_id="open")
        await backend.enter(
            key,
            "draft",
            policy_id="draft",
            policy=PromptPolicy(after_seconds=0.001),
            adapter_key="draft",
            params={},
            session_id=session.session_id,
            expires_at=session.expires_at,
            operation_id="enter",
            enabled=True,
        )
        protected.append(key)
    await asyncio.sleep(0.01)
    assert len(await backend.claim_due(limit=128, lease_seconds=60)) == 128
    terminal = IdleConversationKey("test", 1, 129, 129)
    await backend.open_session(terminal, lifetime_seconds=60, operation_id="terminal")
    old = backend.clock.now() - 120
    # Retain live claims while advancing only the canonical authorization/recovery
    # fields to expired values, without waiting a minute in the test suite.
    for key in [*protected, terminal]:
        record_key = backend._store.keys(key)[0]
        persisted = (await redis_client.get(record_key)).decode()
        hot = json.loads(persisted) if backend._store.format_version == 3 else None
        envelope = decode(hot["state"] if hot is not None else persisted)
        record = envelope["record"]
        activity = (
            replace(record.activity, entered_at=old - 20, last_activity_at=old - 20, expires_at=old)
            if record.activity
            else None
        )
        envelope["record"] = replace(
            record,
            session=replace(record.session, expires_at=old),
            activity=activity,
            recovery_until=old,
        )
        if hot is not None:
            hot["state"] = encode(envelope, schema_version=3)
            persisted = json.dumps(hot)
        else:
            persisted = encode(envelope)
        await redis_client.set(record_key, persisted)
        await redis_client.zadd(
            backend._store.prefix + ":expiry",
            {backend._store.member(key): old + (1 if key == terminal else 0)},
        )
    admitted = IdleConversationKey("test", 1, 130, 130)
    assert await backend.open_session(admitted, lifetime_seconds=30, operation_id="admit")
    assert await backend.load(terminal) is None
    for key in (protected[0], protected[-1]):
        record = await backend.load(key)
        assert record is not None and record.session.expires_at == old


@pytest.mark.parametrize("with_claim", [False, True])
async def test_pre_disable_snapshot_cannot_reserve_effect_after_reenable(
    redis_client, monkeypatch, with_claim
):
    from dataclasses import replace

    from aiogram_idle.errors import VersionConflict
    from aiogram_idle.models import IdleSnapshot, Phase

    backend, key, activity = await setup(redis_client)
    manifest = await backend.bootstrap_config(enabled=True, policies_digest="digest")
    snapshot = await backend.load(key)
    await asyncio.sleep(0.02)
    claim = (await backend.claim_due(limit=1, lease_seconds=30))[0] if with_claim else None

    async def skip_reconcile(*, limit=100):
        return 0

    monkeypatch.setattr(backend, "reconcile", skip_reconcile)
    disabled = await backend.apply_config(
        expected_generation=manifest.generation,
        enabled=False,
        policies_digest="digest",
        operation_id="disable",
    )
    await backend.apply_config(
        expected_generation=disabled.generation,
        enabled=True,
        policies_digest="digest",
        operation_id="enable",
    )
    transformed = False

    def reserve_effect(current):
        nonlocal transformed
        transformed = True
        return replace(current, idle=IdleSnapshot(phase=Phase.PROMPT_PENDING))

    with pytest.raises((VersionConflict, OwnershipLost)):
        await backend.transition(
            key,
            expected_version=snapshot.version,
            operation_id="stale-reserve",
            fingerprint="reserve-before-disable",
            transform=reserve_effect,
            claim=claim,
        )
    assert not transformed
    assert (await backend.lookup_operation(key, "stale-reserve")).status != "found"
    current = await backend.load(key)
    assert current.idle.deadline is None and current.idle.phase == Phase.DISARMED
    # Explicit accepted activity can subsequently arm the new epoch.
    await backend.touch(key, expected=activity.guard, operation_id="fresh-touch", enabled=True)
    assert (await backend.load(key)).idle.phase == Phase.ACTIVE
