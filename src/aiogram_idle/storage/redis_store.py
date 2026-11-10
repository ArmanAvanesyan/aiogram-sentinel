"""Authoritative Redis envelope transactions and startup validation."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Awaitable, Callable, Hashable
from typing import Literal, Protocol, TypeVar, cast

from ..config import IdleConfig
from ..errors import (
    BackendInconsistent,
    ConfigurationMismatch,
    Overloaded,
    OwnershipLost,
    PersistenceUnavailable,
    SessionExpired,
    VersionConflict,
)
from ..models import ConfigManifest, IdleConversationKey, RuntimeSnapshot
from .activation import format_manifest
from .codec import decode, encode
from .deployment import RedisDeploymentAttestation, validate_deployment
from .redis_engine import Engine
from .redis_quarantine import Quarantine
from .redis_scripts import COMMIT, CONFIG, CONFIG_READ, INITIALIZE, READ
from .redis_transport import Connection, RedisClock, array, text
from .state import Claim, OperationReceipt

T = TypeVar("T")


class Fencer(Protocol):
    def __call__(
        self, key: IdleConversationKey, *, scope: object | None = None
    ) -> tuple[str, str] | None: ...


def _unbound_fencer(
    key: IdleConversationKey, *, scope: object | None = None
) -> tuple[str, str] | None:
    if scope is not None:
        raise OwnershipLost("No distributed coordination scope is bound")
    return None


class RedisStore:
    def __init__(
        self,
        redis: object,
        prefix: str,
        config: IdleConfig,
        deployment: RedisDeploymentAttestation | None = None,
    ) -> None:
        if not prefix or len(prefix) > 200 or any(char.isspace() for char in prefix):
            raise ValueError("Redis prefix must be a nonempty bounded string without whitespace")
        self.prefix = prefix
        self.config = config
        self.deployment = deployment
        self.format_version = 1
        self.clock = RedisClock()
        self.connection = Connection(redis, self.clock)
        self.initialized = False
        self.quarantine = Quarantine(self)
        self.created_at = 0.0
        self.history = ""
        self.cursor = "0"
        self.route_cursor = 0
        self.route_scan = "0"
        self.reconcile_pending: list[object] = []
        self.route_pending: list[object] = []
        self.fencer: Fencer = _unbound_fencer

    def member(self, key: IdleConversationKey) -> str:
        return encode(key)

    def ident(self, key: IdleConversationKey) -> str:
        return hashlib.sha256(self.member(key).encode()).hexdigest()

    def route(self, key: IdleConversationKey) -> str:
        return hashlib.sha256(f"{key.namespace}\0{key.bot_id}".encode()).hexdigest()

    def keys(self, key: IdleConversationKey) -> list[str]:
        ident, route = self.ident(key), self.route(key)
        return [
            f"{self.prefix}:record:{ident}",
            f"{self.prefix}:job:{ident}",
            f"{self.prefix}:due:{route}",
            f"{self.prefix}:live",
            f"{self.prefix}:config",
            f"{self.prefix}:routes",
        ]

    def storage_profile(self, *, version: int | None = None) -> str:
        values = {
            "recovery_retention_seconds": float(self.config.recovery_retention_seconds),
            "max_conversations": self.config.max_conversations,
            "max_receipts_per_conversation": self.config.max_receipts_per_conversation,
            "max_tokens_per_conversation": self.config.max_tokens_per_conversation,
            "max_params_bytes": self.config.max_params_bytes,
            "max_components_bytes": self.config.max_components_bytes,
        }
        selected = self.format_version if version is None else version
        if selected == 2:
            values["storage_format"] = 2
        return hashlib.sha256(encode(values).encode()).hexdigest()

    async def initialize(self) -> None:
        if self.initialized:
            return
        await validate_deployment(self.connection, self.deployment)
        self.format_version, _, _ = await format_manifest(self)
        await self.connection.time()
        # Namespace history cannot be silently recreated around retained state.
        marker = await self.connection.script(
            INITIALIZE,
            [
                f"{self.prefix}:created",
                f"{self.prefix}:live",
                f"{self.prefix}:config",
                f"{self.prefix}:expiry",
                f"{self.prefix}:routes",
                f"{self.prefix}:config-established",
                f"{self.prefix}:parked",
            ],
            [self.storage_profile()],
        )
        if text(marker) == "profile-mismatch":
            raise ConfigurationMismatch(
                "Redis replicas require the same storage limits and retention"
            )
        try:
            self.history = text(marker)
            self.created_at = float(self.history.split(":", 1)[0])
            if not math.isfinite(self.created_at) or self.created_at <= 0:
                raise ValueError("Invalid history timestamp")
        except ValueError as error:
            raise BackendInconsistent("Invalid Redis namespace history") from error
        self.config_value(await self.raw_config())
        self.initialized = True

    async def ready(self) -> float:
        await self.initialize()
        marker = await self.connection.call("GET", f"{self.prefix}:created")
        if marker is None or text(marker) != self.history:
            raise BackendInconsistent(
                "Redis namespace history was lost or replaced; explicit recovery required"
            )
        return await self.connection.time()

    async def raw_config(self) -> str:
        value = await self.connection.script(
            CONFIG_READ,
            [
                f"{self.prefix}:config",
                f"{self.prefix}:created",
                f"{self.prefix}:config-established",
            ],
            [self.history],
            mutation=False,
        )
        return text(value)

    def config_envelope(self, raw: str) -> dict[str, object]:
        decoded = decode(raw)
        if not isinstance(decoded, dict):
            raise BackendInconsistent("Invalid Redis configuration envelope")
        data = cast("dict[str, object]", decoded)
        if set(data) != {"manifest", "receipts", "disarm_epoch"} or not isinstance(
            data["manifest"], ConfigManifest
        ):
            raise BackendInconsistent("Invalid Redis configuration manifest")
        if not isinstance(data["disarm_epoch"], str) or len(data["disarm_epoch"]) > 256:
            raise BackendInconsistent("Invalid Redis configuration epoch")
        receipts = data["receipts"]
        if not isinstance(receipts, dict):
            raise BackendInconsistent("Invalid Redis administrative receipts")
        for scope, values in cast("dict[object, object]", receipts).items():
            if scope != "configuration" or not isinstance(values, dict):
                raise BackendInconsistent("Invalid Redis administrative receipt scope")
            for operation_id, receipt in cast("dict[object, object]", values).items():
                if (
                    not isinstance(operation_id, str)
                    or not 1 <= len(operation_id) <= 256
                    or not isinstance(receipt, OperationReceipt)
                    or not isinstance(
                        cast(OperationReceipt[object], receipt).result, ConfigManifest
                    )
                ):
                    raise BackendInconsistent("Invalid Redis administrative receipt")
        return data

    def config_value(self, raw: str) -> ConfigManifest | None:
        return cast(ConfigManifest, self.config_envelope(raw)["manifest"]) if raw else None

    async def read(
        self, key: IdleConversationKey, *, allow_parked: bool = False
    ) -> tuple[Engine, str, str]:
        now = await self.ready()
        if not allow_parked and await self.quarantine.contains(key):
            raise BackendInconsistent(
                "Redis conversation is parked; explicit administrative release required"
            )
        keys = self.keys(key)
        values = array(
            await self.connection.script(
                READ,
                [
                    keys[0],
                    keys[1],
                    keys[3],
                    keys[4],
                    self.prefix + ":created",
                    self.prefix + ":config-established",
                ],
                [self.member(key), self.history],
                mutation=False,
            )
        )
        raw, job, config = (text(value) for value in values[:3])
        if not raw and (job or values[3]):
            raise BackendInconsistent(
                "Retained Redis runtime is missing; administrative recovery required"
            )
        engine = Engine(
            key=key,
            raw=raw,
            job=job,
            manifest=self.config_value(config),
            now=now,
            config=self.config,
            created_at=self.created_at,
            disarm_epoch=cast(str, self.config_envelope(config)["disarm_epoch"]) if config else "",
            storage_format=self.format_version,
        )
        engine.original_job = job
        return engine, raw, config

    async def mutate(
        self,
        key: IdleConversationKey,
        action: Callable[[Engine], Awaitable[T]],
        *,
        claim: Claim | None = None,
        require_live: bool | Literal["session"] = False,
        arm: bool = False,
        coordination_scope: object | None = None,
        expires_at: float | None = None,
    ) -> T:
        fence = self.fencer(key, scope=coordination_scope)
        capacity_pruned = False
        for _ in range(12):
            engine, previous, config = await self.read(key)
            before = await engine.load(key)
            result = await action(engine)
            after = await engine.load(key)
            if arm and after is not None and (before is None or before.version != after.version):
                engine.armed_epoch = engine.disarm_epoch
            expiry = 0.0
            if (
                require_live
                and before is not None
                and after is not None
                and after.version != before.version
            ):
                expiry = min(
                    before.session.expires_at,
                    (
                        after.activity.expires_at
                        if after.activity
                        else before.activity.expires_at
                        if before.activity
                        else before.session.expires_at
                    )
                    if require_live is True
                    else before.session.expires_at,
                )
            if after is not None and (
                before is None or before.session.session_id != after.session.session_id
            ):
                expiry = after.session.expires_at
            if (
                expires_at is not None
                and after is not None
                and (before is None or after.version != before.version)
            ):
                expiry = min(expiry, expires_at) if expiry else expires_at
            status = text(
                await self.connection.script(
                    COMMIT,
                    self.keys(key)
                    + [
                        fence[0] if fence else self.prefix + ":unused-lock",
                        self.prefix + ":expiry",
                        self.prefix + ":created",
                        self.prefix + ":config-established",
                        self.prefix + ":parked",
                    ],
                    [
                        previous,
                        engine.envelope(),
                        engine.job(),
                        self.member(key),
                        self.route(key),
                        config,
                        claim.token if claim else "",
                        claim.generation if claim else 0,
                        self.config.max_conversations,
                        engine.original_job,
                        fence[1] if fence else "",
                        self.retention_check(after),
                        expiry,
                        self.history,
                    ],
                )
            )
            if status == "ok":
                return result
            if status == "expired":
                raise SessionExpired("Authorization expired before Redis commit")
            if status == "ownership":
                raise OwnershipLost("The Redis deadline claim expired or was replaced")
            if status == "capacity" and not capacity_pruned:
                capacity_pruned = True
                budget = self.config.max_conversations
                while budget > 0:
                    batch = min(128, budget)
                    pruned, scanned = await self.prune_expired(limit=batch)
                    budget -= scanned
                    if pruned or scanned < batch:
                        break
                continue
            if status == "capacity":
                raise Overloaded("Redis retained-conversation capacity exhausted; reconcile first")
            if status not in {"conflict", "config"}:
                raise PersistenceUnavailable("Unexpected Redis commit outcome")
        raise VersionConflict("Redis conditional commit remained contended")

    def retention_check(self, record: RuntimeSnapshot | None) -> float:
        if record is None:
            return 0
        now = self.clock.now()
        deadline = max(record.session.expires_at, record.recovery_until)
        if record.idle.operation is not None:
            deadline = max(deadline, now + self.config.recovery_retention_seconds)
        if deadline <= now:
            # A retained expired record has a live claim or unresolved evidence.
            # Rotate only the sweep index, never its authorization/recovery clocks.
            deadline = now + max(1.0, min(60.0, self.config.recovery_retention_seconds))
        return deadline

    async def prune_expired(self, *, limit: int) -> tuple[int, int]:
        now = await self.ready()
        values = array(
            await self.connection.call(
                "ZRANGEBYSCORE", self.prefix + ":expiry", "-inf", now, "LIMIT", 0, limit
            )
        )
        count = 0
        for value in values:
            key = decode(text(value))
            if not isinstance(key, IdleConversationKey):
                raise BackendInconsistent("Invalid Redis expiry identity")

            if await self.quarantine.contains(key):
                await self.connection.call(
                    "ZADD",
                    self.prefix + ":expiry",
                    "XX",
                    "GT",
                    now + 60,
                    self.member(key),
                    mutation=True,
                )
                continue

            async def prune(engine: Engine) -> bool:
                before = await engine.load(engine.key)
                await engine.reconcile(limit=1)
                return before is not None and await engine.load(engine.key) is None

            count += int(await self.mutate(key, prune))
        return count, len(values)

    async def config_change(
        self,
        *,
        enabled: bool,
        policies_digest: str,
        expected: str | None = None,
        operation_id: str | None = None,
    ) -> ConfigManifest:
        for _ in range(12):
            now = await self.ready()
            raw = await self.raw_config()
            engine = Engine(
                key=IdleConversationKey("configuration", 1, 1, 1),
                raw="",
                job="",
                manifest=self.config_value(raw),
                now=now,
                config=self.config,
                created_at=self.created_at,
            )
            if raw:
                data = self.config_envelope(raw)
                engine.restore_configuration_receipts(
                    cast(
                        "dict[Hashable, dict[str, OperationReceipt[object]]]",
                        data.get("receipts", {}),
                    )
                )
            if expected is None:
                manifest = await engine.bootstrap_config(
                    enabled=enabled, policies_digest=policies_digest
                )
            else:
                manifest = await engine.apply_config(
                    expected_generation=expected,
                    enabled=enabled,
                    policies_digest=policies_digest,
                    operation_id=operation_id or "",
                )
            current_manifest = engine.manifest()
            # Successful config reducer sets manifest.
            assert current_manifest is not None  # nosec B101
            previous_manifest = self.config_value(raw)
            epoch = cast(str, self.config_envelope(raw)["disarm_epoch"]) if raw else ""
            if not current_manifest.enabled and (
                previous_manifest is None
                or current_manifest.generation != previous_manifest.generation
            ):
                epoch = current_manifest.generation
            updated = encode(
                {
                    "manifest": current_manifest,
                    "receipts": engine.configuration_receipts(),
                    "disarm_epoch": epoch,
                }
            )
            status = text(
                await self.connection.script(
                    CONFIG,
                    [
                        f"{self.prefix}:config",
                        f"{self.prefix}:created",
                        f"{self.prefix}:config-established",
                    ],
                    [raw, updated, self.history],
                )
            )
            if status == "ok":
                return manifest
        raise VersionConflict("Redis configuration update remained contended")
