"""Managed Redis permissions do not turn deployment safety checks into no-ops."""

from uuid import uuid4

import pytest

from aiogram_nav.errors import ConfigurationError, PersistenceUnavailable
from aiogram_nav.storage.deployment import RedisDeploymentAttestation, validate_deployment
from aiogram_nav.storage.redis_transport import Connection, RedisClock


def attestation():
    return RedisDeploymentAttestation(
        server_major=7,
        writable_primary=True,
        cluster_enabled=False,
        maxmemory_policy="noeviction",
        operator_reference="test-reviewed-deployment",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"server_major": 6},
        {"server_major": True},
        {"writable_primary": False},
        {"cluster_enabled": True},
        {"maxmemory_policy": "allkeys-lru"},
        {"operator_reference": ""},
    ],
)
def test_unsafe_operator_attestation_is_rejected(changes):
    values = dict(
        server_major=7,
        writable_primary=True,
        cluster_enabled=False,
        maxmemory_policy="noeviction",
        operator_reference="change-123",
    )
    with pytest.raises(ConfigurationError):
        RedisDeploymentAttestation(**(values | changes))


async def test_permission_denials_require_explicit_attestation(nav_redis_client, nav_redis_url):
    from redis.asyncio import Redis

    from aiogram_nav.storage.redis import RedisNavigationRepository

    user = "idle-attested-" + uuid4().hex
    password = uuid4().hex
    prefix = "managed:" + uuid4().hex
    await nav_redis_client.execute_command(
        "ACL",
        "SETUSER",
        user,
        "on",
        ">" + password,
        "~" + prefix + ":*",
        "+@all",
        "-info",
        "-role",
        "-config",
    )
    client = Redis.from_url(nav_redis_url, username=user, password=password, decode_responses=False)
    try:
        strict = RedisNavigationRepository(redis=client, prefix=prefix)
        with pytest.raises(PersistenceUnavailable):
            await strict.initialize()
        backend = RedisNavigationRepository(redis=client, prefix=prefix, deployment=attestation())
        await backend.initialize()
        from tests.test_redis_backend import enter

        await enter(backend)
        await backend.close()
        assert await client.ping()  # Caller-owned client remains usable.
    finally:
        await client.aclose()
        await nav_redis_client.execute_command("ACL", "DELUSER", user)


@pytest.mark.parametrize(
    "command,response",
    [
        (("INFO", "server"), {"redis_version": "6.2.0"}),
        (("INFO", "cluster"), {"cluster_enabled": 1}),
        (("ROLE",), [b"slave"]),
        (("CONFIG", "GET", "maxmemory-policy"), [b"maxmemory-policy", b"allkeys-lru"]),
    ],
)
async def test_attestation_never_overrides_observed_unsafe_facts(
    nav_redis_client, command, response
):
    class Observation:
        async def execute_command(self, *args):
            return response if args == command else await nav_redis_client.execute_command(*args)

    with pytest.raises(ConfigurationError):
        await validate_deployment(Connection(Observation(), RedisClock()), attestation())


async def test_attestation_does_not_hide_connection_failure():
    class Offline:
        async def execute_command(self, *args):
            raise ConnectionError("offline")

    with pytest.raises(PersistenceUnavailable):
        await validate_deployment(Connection(Offline(), RedisClock()), attestation())
