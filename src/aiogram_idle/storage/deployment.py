"""Explicit deployment facts for managed Redis that denies introspection."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ..errors import ConfigurationMismatch, PersistenceUnavailable
from .redis_transport import Connection, array, text


@dataclass(frozen=True)
class RedisDeploymentAttestation:
    """Operator-verified facts, never permission to override contrary observations."""

    server_major: int
    writable_primary: bool
    cluster_enabled: bool
    maxmemory_policy: str
    operator_reference: str

    def __post_init__(self) -> None:
        if type(self.server_major) is not int or self.server_major < 7:
            raise ConfigurationMismatch("Attestation requires Redis 7 or newer")
        if self.writable_primary is not True or self.cluster_enabled is not False:
            raise ConfigurationMismatch("Attestation requires a writable non-cluster primary")
        if self.maxmemory_policy != "noeviction":
            raise ConfigurationMismatch("Attestation requires noeviction")
        if (
            not isinstance(cast(object, self.operator_reference), str)
            or not self.operator_reference
            or len(self.operator_reference) > 256
        ):
            raise ConfigurationMismatch("Attestation requires a bounded operator reference")


def _denied(error: Exception) -> bool:
    cause: BaseException | None = error
    while cause is not None:
        if any(cls.__name__ == "NoPermissionError" for cls in type(cause).__mro__):
            return True
        if any(cls.__name__ == "ResponseError" for cls in type(cause).__mro__) and str(
            cause
        ).upper().startswith("NOPERM"):
            return True
        cause = cause.__cause__
    return False


def _info(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return dict(line.split(":", 1) for line in text(value).splitlines() if ":" in line)


async def validate_deployment(
    connection: Connection, attestation: RedisDeploymentAttestation | None
) -> None:
    """Only an actual permission denial permits substitution of attested facts."""

    async def inspect(*command: str) -> object | None:
        try:
            return await connection.call(*command)
        except PersistenceUnavailable as error:
            if attestation is None or not _denied(error):
                raise
            logging.getLogger(__name__).warning(
                "Redis introspection denied; using explicit operator attestation for %s",
                " ".join(command[:2]),
            )
            return None

    server = await inspect("INFO", "server")
    if server is not None:
        try:
            major = int(str(_info(server).get("redis_version", "0")).split(".")[0])
        except ValueError as error:
            raise ConfigurationMismatch("Redis version response is malformed") from error
        if major < 7:
            raise ConfigurationMismatch("Reliable backend requires Redis 7 or newer")
    role = await inspect("ROLE")
    if role is not None and (not array(role) or text(array(role)[0]) != "master"):
        raise ConfigurationMismatch("Redis backend requires a writable primary")
    cluster = await inspect("INFO", "cluster")
    if cluster is not None:
        facts = _info(cluster)
        if "cluster_enabled" not in facts:
            raise ConfigurationMismatch("Redis cluster response is malformed")
        if str(facts["cluster_enabled"]) != "0":
            raise ConfigurationMismatch("Redis Cluster is not supported")
    eviction = await inspect("CONFIG", "GET", "maxmemory-policy")
    if eviction is not None:
        if isinstance(eviction, dict):
            policy = cast(dict[str, object], eviction).get("maxmemory-policy")
        else:
            values = array(eviction)
            policy = values[1] if len(values) == 2 else None
        if policy is None or text(policy) != "noeviction":
            raise ConfigurationMismatch("Reliable backend requires maxmemory-policy noeviction")
