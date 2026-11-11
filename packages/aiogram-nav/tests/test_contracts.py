"""Immutable identities, JSON boundaries, and strict persistence formats."""

import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

import pytest

from aiogram_nav.clock import ManualClock
from aiogram_nav.codec import decode, encode, loads_snapshot
from aiogram_nav.config import NavigationConfig
from aiogram_nav.errors import (
    ConfigurationError,
    InvalidParameters,
    SchemaUnsupported,
    UnsupportedContext,
)
from aiogram_nav.json import freeze_object, timestamp_ms
from aiogram_nav.models import (
    ConversationKey,
    EffectCheckpoint,
    HistoryEntry,
    MessageRef,
    NavigationAction,
    NavigationIntent,
    NavigationMutation,
    NavigationSnapshot,
    NavigationToken,
    PreparedAction,
    RenderResult,
    ViewState,
)


def snapshot():
    return NavigationSnapshot(
        "session",
        "main",
        {"nested": [1, {"x": True}]},
        1,
        1,
        1000,
        1000,
        2000,
        ViewState("view", (MessageRef(2, 3),)),
    )


def test_snapshot_freezes_nested_inputs_and_history():
    data = {"items": [1]}
    value = replace(snapshot(), params=data, history=[HistoryEntry("main", data)])
    data["items"].append(2)
    assert value.params["items"] == (1,)
    assert value.history[0].params["items"] == (1,)
    with pytest.raises(TypeError):
        value.params["items"] = ()
    with pytest.raises(FrozenInstanceError):
        value.node_id = "other"


@pytest.mark.parametrize(
    "kwargs", [{"chat_id": -1}, {"bot_id": True}, {"user_id": 3}, {"namespace": ""}]
)
def test_invalid_identity(kwargs):
    data = dict(namespace="test", bot_id=1, chat_id=2, user_id=2)
    data.update(kwargs)
    with pytest.raises((ValueError, UnsupportedContext)):
        ConversationKey(**data)


@pytest.mark.parametrize(
    "value", [{"a": float("nan")}, {1: "bad"}, {"a": object()}, {"a": float("inf")}]
)
def test_non_json_parameters_rejected(value):
    with pytest.raises(InvalidParameters):
        freeze_object(value)


def test_parameter_size_and_depth_bounds():
    with pytest.raises(InvalidParameters):
        freeze_object({"x": "a" * 100}, max_bytes=10)
    value = {}
    for _ in range(35):
        value = {"x": value}
    with pytest.raises(InvalidParameters):
        freeze_object(value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"session_seconds": 0},
        {"recovery_seconds": float("inf")},
        {"history_limit": -1},
        {"max_tokens": True},
        {"max_params_bytes": 0},
        {"history_limit": 1001},
    ],
)
def test_configuration_validation(kwargs):
    with pytest.raises(ConfigurationError):
        NavigationConfig(**kwargs)


def test_zero_history_and_utc_boundaries():
    assert NavigationConfig(history_limit=0).history_limit == 0
    assert timestamp_ms(datetime(1970, 1, 1, tzinfo=timezone.utc)) == 0
    with pytest.raises(ValueError):
        timestamp_ms(datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        timestamp_ms(True)


def test_codec_round_trip_nested_snapshots_and_ledger():
    key = ConversationKey("test", 1, 2, 2, tenant_id="tenant")
    rendered = RenderResult("view", (MessageRef(2, 3),), "tray", "hy", "ru")
    prepared = PreparedAction(
        key,
        NavigationIntent("go", "main", {"x": [1]}),
        "session",
        "view",
        None,
        2000,
        1000,
        "fingerprint",
        effects={"send": EffectCheckpoint("send", "confirmed", rendered)},
        rendered=rendered,
    )
    assert decode(encode(prepared)) == prepared
    assert loads_snapshot(encode(snapshot())) == snapshot()
    assert decode(encode({"type": "NavigationSnapshot", "value": [1]})) == {
        "type": "NavigationSnapshot",
        "value": [1],
    }


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        '{"schema_version":1,"value":1,"extra":2}',
        '{"schema_version":1,"schema_version":1,"value":1}',
        '{"schema_version":1,"value":NaN}',
        '{"schema_version":1,"value":{"type":"tuple","value":{}}}',
    ],
)
def test_malformed_records_rejected(raw):
    with pytest.raises(ConfigurationError):
        decode(raw)


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":4,"value":1}',
        '{"schema_version":1,"value":{"type":"FutureType","value":{}}}',
    ],
)
def test_newer_schemas_are_distinct(raw):
    with pytest.raises(SchemaUnsupported):
        decode(raw)


def test_codec_rejects_bool_revisions_and_inconsistent_generations():
    value = json.loads(encode(snapshot()))
    value["value"]["value"]["nav_revision"] = True
    with pytest.raises(ConfigurationError):
        decode(json.dumps(value))
    with pytest.raises(ValueError):
        replace(snapshot(), expires_at=1000)


def test_message_and_token_ownership_validation():
    key = ConversationKey("test", 1, 2, 2)
    with pytest.raises(ValueError):
        MessageRef(2, 0)
    with pytest.raises(UnsupportedContext):
        NavigationToken("token", key, 3, "session", "view", NavigationAction(), 1000)
    with pytest.raises(ValueError):
        NavigationToken("t" * 49, key, 2, "session", "view", NavigationAction(), 1000)


def test_prepared_effects_defensively_copied():
    key = ConversationKey("test", 1, 2, 2)
    effects = {"send": EffectCheckpoint("send", "started")}
    value = PreparedAction(
        key,
        NavigationIntent("op", "main"),
        "s",
        "v",
        None,
        2000,
        1000,
        "fingerprint",
        effects=effects,
    )
    effects.clear()
    assert "send" in value.effects
    assert value.operation_id == "op" and value.node_id == "main"


async def test_manual_clock_milliseconds_and_monotonic():
    clock = ManualClock(1000)
    clock.advance(500)
    assert clock.now() == clock.now_ms() == 1500
    assert clock.monotonic() == 0.5
    await clock.sleep(0.1)
    assert clock.now() == 1600
    with pytest.raises(ValueError):
        clock.advance(-1)


def test_action_mutation_values_are_validated():
    with pytest.raises(ValueError):
        NavigationAction(kind="future")
    with pytest.raises(ValueError):
        NavigationMutation("op", "s", kind="future")
    with pytest.raises(ValueError):
        EffectCheckpoint("send", "future")


async def test_coordinator_capabilities_are_task_scoped_and_expire():
    import asyncio

    from aiogram_nav.isolation import MemoryCoordinator

    coord = MemoryCoordinator()
    key, other = ConversationKey("test", 1, 2, 2), ConversationKey("test", 1, 3, 3)
    async with coord.hold(key):
        token = coord.scope_token(key)
        assert token is not None and coord.scope_matches(key, token)
        assert not coord.scope_matches(other, token)
        async with coord.hold(key):
            assert coord.scope_token(key) is token

        async def child():
            assert coord.scope_token(key) is None
            assert not coord.owns(key)
            assert coord.scope_matches(key, token)

        await asyncio.create_task(child())
    assert not coord.scope_active(token)
    assert not coord.scope_matches(key, token)
    assert coord.active_scopes == coord.lock_count == 0


async def test_cancelled_coordinator_waiters_do_not_leak_locks():
    import asyncio

    from aiogram_nav.isolation import MemoryCoordinator

    coord = MemoryCoordinator()
    key = ConversationKey("test", 1, 2, 2)

    async def wait():
        async with coord.hold(key):
            raise AssertionError("cancelled waiter acquired scope")

    async with coord.hold(key):
        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        assert coord.active_scopes == 2
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert coord.active_scopes == 1
    assert coord.active_scopes == coord.lock_count == 0


def test_newer_snapshot_record_version_is_not_reinterpreted():
    raw = json.loads(encode(snapshot()))
    raw["value"]["value"]["schema_version"] = 2
    with pytest.raises(SchemaUnsupported):
        decode(json.dumps(raw))


@pytest.mark.parametrize("malformed", ["\ud800", "\ud83d\ude00"])
def test_persistable_strings_reject_surrogate_code_units_early(malformed):
    from aiogram_nav import ConversationKey, InvalidParameters, NavigationIntent, Node
    from aiogram_nav.json import freeze_object

    with pytest.raises(ValueError):
        Node(malformed)
    with pytest.raises(ValueError):
        ConversationKey(malformed, 1, 2, 2)
    with pytest.raises(ValueError):
        NavigationIntent(malformed, "main")
    with pytest.raises(InvalidParameters):
        freeze_object({"value": malformed})
    with pytest.raises(InvalidParameters):
        freeze_object({malformed: "value"})


def test_non_bmp_unicode_scalars_survive_strict_codec():
    from aiogram_nav.codec import decode, encode

    assert decode(encode({"Հայերեն": "😀"})) == {"Հայերեն": "😀"}
    assert decode('{"schema_version":3,"value":"\\ud83d\\ude00"}') == "😀"
