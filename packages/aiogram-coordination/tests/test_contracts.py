"""Validate public, immutable contracts and external-session boundaries."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from aiogram_coordination import (
    ConfigurationError,
    CoordinationKey,
    ExternalSession,
    RedisCoordinator,
    coordination_key,
    validate_session_transition,
)


@pytest.mark.parametrize(
    "field,value",
    [
        ("namespace", ""),
        ("namespace", 1),
        ("namespace", "x" * 129),
        ("bot_id", True),
        ("chat_id", 0),
        ("user_id", -1),
        ("tenant_id", ""),
        ("tenant_id", 3),
        ("tenant_id", "x" * 129),
    ],
)
def test_identity_rejects_ambiguous_values(field, value):
    values = dict(namespace="test", bot_id=1, chat_id=2, user_id=2, tenant_id=None)
    values[field] = value
    with pytest.raises(ConfigurationError):
        CoordinationKey(**values)


def test_structural_keys_preserve_all_dimensions_and_lock_encoding():
    key = CoordinationKey("test", 1, 2, 2, "tenant")
    assert coordination_key(key) is key
    assert coordination_key(SimpleNamespace(**key.__dict__)) == key
    with pytest.raises(ConfigurationError):
        coordination_key(object())
    with pytest.raises(FrozenInstanceError):
        key.bot_id = 5
    coordinator = RedisCoordinator(redis=object(), prefix="old")
    import hashlib
    import json

    digest = hashlib.sha256(
        json.dumps(["test", "tenant", 1, 2, 2], separators=(",", ":")).encode()
    ).hexdigest()
    assert coordinator.lock_key(key) == "old:conversation-lock:" + digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", ""),
        ("session_id", 1),
        ("revision", ""),
        ("absolute_expires_at", None),
        ("absolute_expires_at", True),
        ("absolute_expires_at", 0),
        ("absolute_expires_at", 253402300800000),
        ("idle_expires_at", 0),
        ("idle_expires_at", 1001),
    ],
)
def test_session_validation(field, value):
    values = dict(
        session_id="session", revision="1", absolute_expires_at=1000, idle_expires_at=None
    )
    values[field] = value
    with pytest.raises(ConfigurationError):
        ExternalSession(**values)


def test_external_session_effective_expiry_does_not_extend_absolute_lifetime():
    original = ExternalSession("s", "1", 1000, 100)
    current = ExternalSession("s", "2", 1000, 500)
    validate_session_transition(original, current)
    assert current.expires_at == 500 and current.absolute_expires_at == 1000
    assert current.is_live(499) and not current.is_live(500)
    assert ExternalSession("s2", "1", 2000).expires_at == 2000
    with pytest.raises(ConfigurationError):
        current.is_live(True)
    with pytest.raises(ConfigurationError):
        validate_session_transition(current, ExternalSession("s", "3", 2000))
    validate_session_transition(current, ExternalSession("new-id", "1", 2000))


@pytest.mark.parametrize(
    "name,value",
    [
        ("lease_seconds", 0),
        ("lease_seconds", True),
        ("lease_seconds", float("inf")),
        ("lease_seconds", 0.01),
        ("renew_seconds", -1),
        ("io_timeout", 30),
        ("prefix", "bad prefix"),
        ("prefix", ""),
        ("prefix", "x" * 257),
    ],
)
def test_coordinator_configuration_is_bounded(name, value):
    with pytest.raises(ConfigurationError):
        RedisCoordinator(redis=object(), **{name: value})


@pytest.mark.parametrize(
    "extra", [{"thread_id": 1}, {"business_connection_id": "business"}, {"destiny": "other"}]
)
def test_structural_conversion_never_discards_fsm_identity(extra):
    with pytest.raises(ConfigurationError):
        coordination_key(
            SimpleNamespace(namespace="n", tenant_id=None, bot_id=1, chat_id=2, user_id=2, **extra)
        )
