"""Corrupt authoritative Redis values fail closed before a conditional write."""

import json
from uuid import uuid4

import pytest

from aiogram_idle.errors import BackendInconsistent, SchemaUnsupported
from aiogram_idle.models import IdleConversationKey
from aiogram_idle.policies import PromptPolicy
from aiogram_idle.storage.codec import decode, encode
from aiogram_idle.storage.redis import RedisIdleBackend
from aiogram_idle.storage.state import ControlToken


@pytest.fixture
async def seeded(redis_client):
    prefix = f"test:corruption:{uuid4().hex}"
    backend = RedisIdleBackend(redis=redis_client, prefix=prefix)
    await backend.initialize()
    key = IdleConversationKey("corruption", 1, 42, 42)
    session = await backend.open_session(key, lifetime_seconds=300, operation_id="open")
    activity = await backend.enter(
        key,
        "draft",
        policy_id="prompt",
        policy=PromptPolicy(),
        adapter_key="draft",
        params={},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
        enabled=True,
    )
    yield backend, redis_client, key, activity, backend._store.keys(key)
    keys = [item async for item in redis_client.scan_iter(match=f"{prefix}:*")]
    if keys:
        await redis_client.delete(*keys)
    await backend.close()


async def retained_values(client, keys):
    return [await client.dump(key) for key in keys]


async def rejected_without_mutation(seeded):
    backend, client, key, activity, keys = seeded
    before = await retained_values(client, keys)
    with pytest.raises((BackendInconsistent, SchemaUnsupported)):
        await backend.touch(
            key, expected=activity.guard, operation_id="corrupted-touch", enabled=True
        )
    assert await retained_values(client, keys) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", True),
        ("generation", 0),
        ("generation", -1),
        ("generation", 1.5),
        ("deadline", True),
        ("deadline", float("nan")),
        ("deadline", float("inf")),
        ("eligible_at", False),
        ("eligible_at", float("-inf")),
        ("lease_until", True),
        ("lease_until", float("nan")),
        ("token", ""),
        ("token", 23),
    ],
)
async def test_invalid_job_fields_fail_closed(seeded, field, value):
    _, client, _, _, keys = seeded
    job = json.loads(await client.get(keys[1]))
    job[field] = value
    await client.set(keys[1], json.dumps(job))
    await rejected_without_mutation(seeded)


@pytest.mark.parametrize("body", ["{", "[]", "null", '{"generation":1}'])
async def test_malformed_job_fails_closed(seeded, body):
    _, client, _, _, keys = seeded
    await client.set(keys[1], body)
    await rejected_without_mutation(seeded)


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy", "prompt"),
        ("policy", {"after_seconds": 600}),
        ("receipts", []),
        ("receipts", {"open": True}),
        ("tokens", []),
        ("tokens", {"token": True}),
        ("pruned_before", True),
        ("pruned_before", "yesterday"),
    ],
)
async def test_invalid_envelope_fields_fail_closed(seeded, field, value):
    _, client, _, _, keys = seeded
    envelope = decode((await client.get(keys[0])).decode())
    envelope[field] = value
    await client.set(keys[0], encode(envelope))
    await rejected_without_mutation(seeded)


async def test_missing_envelope_field_fails_closed(seeded):
    _, client, _, _, keys = seeded
    envelope = decode((await client.get(keys[0])).decode())
    del envelope["receipts"]
    await client.set(keys[0], encode(envelope))
    await rejected_without_mutation(seeded)


async def test_wrong_runtime_identity_fails_closed(seeded):
    backend, client, _, _, keys = seeded
    other = IdleConversationKey("other", 1, 99, 99)
    await backend.open_session(other, lifetime_seconds=300, operation_id="other-open")
    await client.set(keys[0], await client.get(backend._store.keys(other)[0]))
    await rejected_without_mutation(seeded)


async def test_wrong_control_identity_fails_closed(seeded):
    _, client, key, activity, keys = seeded
    envelope = decode((await client.get(keys[0])).decode())
    token = ControlToken(
        IdleConversationKey("wrong", 1, 42, 42),
        "token",
        "prompt",
        activity.session_id,
        activity.activity_id,
        9999999999,
    )
    assert token.key != key
    envelope["tokens"] = {"token": token}
    await client.set(keys[0], encode(envelope))
    await rejected_without_mutation(seeded)


async def test_wrong_control_token_index_fails_closed(seeded):
    _, client, key, activity, keys = seeded
    envelope = decode((await client.get(keys[0])).decode())
    token = ControlToken(
        key, "actual", "prompt", activity.session_id, activity.activity_id, 9999999999
    )
    envelope["tokens"] = {"different": token}
    await client.set(keys[0], encode(envelope))
    await rejected_without_mutation(seeded)


@pytest.mark.parametrize("version", [0, 3, True, "1"])
async def test_unsupported_runtime_schema_fails_closed(seeded, version):
    _, client, _, _, keys = seeded
    envelope = json.loads(await client.get(keys[0]))
    envelope["schema_version"] = version
    await client.set(keys[0], json.dumps(envelope))
    await rejected_without_mutation(seeded)


async def test_extra_envelope_field_fails_closed(seeded):
    _, client, _, _, keys = seeded
    envelope = decode((await client.get(keys[0])).decode())
    envelope["future_semantics"] = True
    await client.set(keys[0], encode(envelope))
    await rejected_without_mutation(seeded)


async def test_extra_job_field_fails_closed(seeded):
    _, client, _, _, keys = seeded
    job = json.loads(await client.get(keys[1]))
    job["unexpected"] = True
    await client.set(keys[1], json.dumps(job))
    await rejected_without_mutation(seeded)


async def test_missing_active_policy_fails_closed(seeded):
    _, client, _, _, keys = seeded
    envelope = decode((await client.get(keys[0])).decode())
    envelope["policy"] = None
    await client.set(keys[0], encode(envelope))
    await rejected_without_mutation(seeded)
