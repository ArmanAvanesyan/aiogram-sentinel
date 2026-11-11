"""Authoritative namespace, manifest and quarantine fences at execution time."""

import hashlib
from uuid import uuid4

import pytest

from aiogram_idle import IdleConversationKey, PromptPolicy
from aiogram_idle.errors import BackendInconsistent, PersistenceUnavailable
from aiogram_idle.storage.redis import RedisIdleBackend
from aiogram_idle.storage.redis_scripts import CLAIM, COMMIT, CONFIG, LEASE, READ
from aiogram_idle.storage.redis_transport import Connection, RedisClock


class BeforeScript:
    def __init__(self, client):
        self.client = client
        self.target = None
        self.callback = None
        self.lease_commands = []

    async def execute_command(self, *args):
        if (
            args[0] == "EVALSHA"
            and args[1] == hashlib.sha1(LEASE.encode(), usedforsecurity=False).hexdigest()
        ):
            self.lease_commands.append(args)
        if args[0] == "EVALSHA" and self.target == args[1] and self.callback:
            callback, self.callback = self.callback, None
            await callback()
        return await self.client.execute_command(*args)

    def intercept(self, source, callback):
        self.target = hashlib.sha1(source.encode(), usedforsecurity=False).hexdigest()
        self.callback = callback


async def seed(client):
    wrapped = BeforeScript(client)
    backend = RedisIdleBackend(redis=wrapped, prefix=f"audit-commit:{uuid4().hex}")
    await backend.bootstrap_config(enabled=True, policies_digest="policy")
    key = IdleConversationKey("audit", 1, 2, 2)
    session = await backend.open_session(key, lifetime_seconds=100, operation_id="open")
    activity = await backend.enter(
        key,
        "draft",
        policy_id="draft",
        policy=PromptPolicy(),
        adapter_key="form",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )
    return wrapped, backend, key, activity


@pytest.mark.parametrize("replacement", [None, "another-namespace"])
async def test_history_is_fenced_inside_commit(redis_client, replacement):
    wrapped, backend, key, activity = await seed(redis_client)
    record_key = backend._store.keys(key)[0]
    before = await redis_client.get(record_key)

    async def lose_history():
        if replacement is None:
            await redis_client.delete(backend._store.prefix + ":created")
        else:
            await redis_client.set(backend._store.prefix + ":created", replacement)

    wrapped.intercept(COMMIT, lose_history)
    with pytest.raises(BackendInconsistent):
        await backend.touch(key, expected=activity.guard, operation_id="stale-namespace")
    assert await redis_client.get(record_key) == before


@pytest.mark.parametrize("source", [READ, CLAIM, LEASE, CONFIG])
async def test_all_execution_stages_reject_lost_namespace(redis_client, source):
    from dataclasses import replace

    wrapped, backend, key, _ = await seed(redis_client)
    record = await backend.load(key)
    await backend.transition(
        key,
        expected_version=record.version,
        operation_id="due",
        fingerprint="due",
        transform=lambda old: replace(old, idle=replace(old.idle, deadline=0)),
    )
    claim = None
    if source == LEASE:
        (claim,) = await backend.claim_due(limit=1, lease_seconds=10)

    async def lose_history():
        await redis_client.delete(backend._store.prefix + ":created")

    wrapped.intercept(source, lose_history)
    with pytest.raises(BackendInconsistent):
        if source == READ:
            await backend.load(key)
        elif source == CLAIM:
            await backend.claim_due(limit=1, lease_seconds=10)
        elif source == LEASE:
            await backend.renew_claim(claim, lease_seconds=10)
        else:
            manifest = await backend.get_config()
            await backend.apply_config(
                expected_generation=manifest.generation,
                enabled=False,
                policies_digest="policy",
                operation_id="disable",
            )


async def test_missing_established_configuration_cannot_bootstrap_defaults(redis_client):
    _, backend, _, _ = await seed(redis_client)
    await redis_client.delete(backend._store.prefix + ":config")
    with pytest.raises(BackendInconsistent):
        await backend.bootstrap_config(enabled=True, policies_digest="other-default")
    other = RedisIdleBackend(redis=redis_client, prefix=backend._store.prefix)
    with pytest.raises(BackendInconsistent):
        await other.initialize()
    assert await redis_client.get(backend._store.prefix + ":config") is None


async def test_configuration_loss_between_read_and_commit_fails_closed(redis_client):
    wrapped, backend, key, activity = await seed(redis_client)
    before = await redis_client.get(backend._store.keys(key)[0])

    async def lose_config():
        await redis_client.delete(backend._store.prefix + ":config")

    wrapped.intercept(COMMIT, lose_config)
    with pytest.raises(BackendInconsistent):
        await backend.touch(key, expected=activity.guard, operation_id="lost-config")
    assert await redis_client.get(backend._store.keys(key)[0]) == before


async def test_parked_flag_fences_inflight_writer(redis_client):
    wrapped, backend, key, activity = await seed(redis_client)
    before = await redis_client.get(backend._store.keys(key)[0])

    async def park():
        await redis_client.hset(
            backend._store.prefix + ":parked", backend._store.member(key), "audit"
        )

    wrapped.intercept(COMMIT, park)
    with pytest.raises(BackendInconsistent):
        await backend.touch(key, expected=activity.guard, operation_id="after-quarantine")
    assert await redis_client.get(backend._store.keys(key)[0]) == before


@pytest.mark.parametrize("marker", ["NaN", "inf", "invalid", "-1"])
async def test_invalid_namespace_history_is_typed(redis_client, marker):
    prefix = f"audit-marker:{uuid4().hex}"
    await redis_client.set(prefix + ":created", marker)
    backend = RedisIdleBackend(redis=redis_client, prefix=prefix)
    with pytest.raises(BackendInconsistent):
        await backend.initialize()


@pytest.mark.parametrize("mutation", [False, True])
async def test_script_error_after_noscript_reload_retains_consistent_type(mutation):
    class NoScriptError(Exception):
        pass

    class ResponseError(Exception):
        pass

    class Client:
        attempts = 0

        async def execute_command(self, *args):
            if args[0] == "SCRIPT":
                return "sha"
            self.attempts += 1
            if self.attempts == 1:
                raise NoScriptError()
            raise ResponseError("script runtime failed")

    connection = Connection(Client(), RedisClock())
    with pytest.raises(BackendInconsistent):
        await connection.script("return 1", [], [], mutation=mutation)


async def test_noscript_reload_is_bounded():
    class NoScriptError(Exception):
        pass

    class Client:
        attempts = 0

        async def execute_command(self, *args):
            if args[0] == "SCRIPT":
                return "sha"
            self.attempts += 1
            raise NoScriptError()

    client = Client()
    with pytest.raises(PersistenceUnavailable):
        await Connection(client, RedisClock()).script("return 1", [], [])
    assert client.attempts == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("recovery_retention_seconds", 1),
        ("max_conversations", 1),
        ("max_receipts_per_conversation", 1),
        ("max_tokens_per_conversation", 1),
        ("max_params_bytes", 100),
    ],
)
async def test_replica_storage_profile_mismatch_rejected(redis_client, field, value):
    from aiogram_idle import ConfigurationMismatch, IdleConfig

    _, backend, _, _ = await seed(redis_client)
    other = RedisIdleBackend(
        redis=redis_client, prefix=backend._store.prefix, config=IdleConfig(**{field: value})
    )
    with pytest.raises(ConfigurationMismatch):
        await other.initialize()


async def test_runtime_only_configuration_does_not_change_storage_profile(redis_client):
    from aiogram_idle import IdleConfig

    _, backend, _, _ = await seed(redis_client)
    other = RedisIdleBackend(
        redis=redis_client,
        prefix=backend._store.prefix,
        config=IdleConfig(enabled=False, poll_seconds=3, recovery_retention_seconds=3600.0),
    )
    await other.initialize()
    assert (await other.get_config()).enabled


async def test_replaying_older_heartbeat_after_newer_one_cannot_extend_lease(redis_client):
    import asyncio
    import json
    from dataclasses import replace

    wrapped, backend, key, _ = await seed(redis_client)
    record = await backend.load(key)
    await backend.transition(
        key,
        expected_version=record.version,
        operation_id="due",
        fingerprint="due",
        transform=lambda old: replace(old, idle=replace(old.idle, deadline=0)),
    )
    (claim,) = await backend.claim_due(limit=1, lease_seconds=10)
    await backend.renew_claim(claim, lease_seconds=10)
    old_request = wrapped.lease_commands[-1]
    await asyncio.sleep(0.02)
    newer = await backend.renew_claim(claim, lease_seconds=10)
    await asyncio.sleep(0.02)
    replay = json.loads(await redis_client.execute_command(*old_request))
    assert replay["lease_until"] == newer.lease_until


async def test_quarantine_does_not_park_a_repaired_newer_snapshot(redis_client):
    import json

    from aiogram_idle.errors import SchemaUnsupported

    _, backend, key, _ = await seed(redis_client)
    record_key = backend._store.keys(key)[0]
    original = await redis_client.get(record_key)
    broken = json.loads(original)
    if backend._store.format_version == 3:
        state = json.loads(broken["state"])
        state["schema_version"] = 999
        broken["state"] = json.dumps(state)
    else:
        broken["schema_version"] = 999
    await redis_client.set(record_key, json.dumps(broken))
    with pytest.raises(SchemaUnsupported):
        await backend.load(key)
    await redis_client.set(record_key, original)
    await backend._store.quarantine.park(key, reason="SchemaUnsupported")
    assert not await backend._store.quarantine.contains(key)
    assert (await backend.load(key)).activity is not None


async def test_binary_corruption_can_be_parked_without_losing_evidence(redis_client):
    from aiogram_idle.errors import SchemaUnsupported

    _, backend, key, _ = await seed(redis_client)
    record_key = backend._store.keys(key)[0]
    broken = b"\xffinvalid-encoding"
    await redis_client.set(record_key, broken)
    with pytest.raises(SchemaUnsupported):
        await backend.load(key)
    await backend._store.quarantine.park(key, reason="SchemaUnsupported")
    assert await backend._store.quarantine.contains(key)
    assert await redis_client.get(record_key) == broken


@pytest.mark.parametrize("error_kind", ["ReadOnlyError", "OutOfMemoryError", "NoPermissionError"])
@pytest.mark.parametrize("reload", [False, True])
async def test_server_error_subclasses_are_never_uncertain_transport_errors(error_kind, reload):
    exceptions = pytest.importorskip("redis.exceptions")

    class Client:
        attempts = 0

        async def execute_command(self, *args):
            if args[0] == "SCRIPT":
                return "sha"
            self.attempts += 1
            if reload and self.attempts == 1:
                raise exceptions.NoScriptError()
            raise getattr(exceptions, error_kind)("server rejected execution")

    with pytest.raises(BackendInconsistent):
        await Connection(Client(), RedisClock()).script("return 1", [], [])


async def test_changed_job_snapshot_is_not_claimed_or_overwritten(redis_client):
    from dataclasses import replace

    wrapped, backend, key, _ = await seed(redis_client)
    record = await backend.load(key)
    await backend.transition(
        key,
        expected_version=record.version,
        operation_id="due",
        fingerprint="due",
        transform=lambda old: replace(old, idle=replace(old.idle, deadline=0)),
    )
    job_key = backend._store.keys(key)[1]
    invalid = b'{"generation":-1,"deadline":0,"eligible_at":0,"lease_until":0}'

    async def replace_job():
        await redis_client.set(job_key, invalid)

    wrapped.intercept(CLAIM, replace_job)
    assert await backend.claim_due(limit=1, lease_seconds=10) == []
    assert await redis_client.get(job_key) == invalid
