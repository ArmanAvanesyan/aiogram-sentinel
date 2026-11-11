"""Redis lease operations and bounded reconciliation."""

from __future__ import annotations

import math
import secrets
from dataclasses import replace

from ..errors import BackendInconsistent, OwnershipLost, SchemaUnsupported
from ..models import IdleConversationKey, IdleSnapshot, Phase
from .codec import decode
from .redis_engine import Engine, job_decode
from .redis_scripts import CLAIM, LEASE
from .redis_store import RedisStore
from .redis_transport import array, text
from .state import Claim


class RedisJobs:
    _store: RedisStore

    async def claim_due(
        self,
        *,
        limit: int,
        lease_seconds: float,
        namespace: str | None = None,
        bot_id: int | None = None,
    ) -> list[Claim]:
        if (
            isinstance(limit, bool)
            or limit < 1
            or not math.isfinite(lease_seconds)
            or lease_seconds <= 0
        ):
            raise ValueError("Claim capacity and lease must be positive")
        store = self._store
        now = await store.ready()
        store.config_value(await store.raw_config())
        if store.format_version == 3:
            from .canonical_gc import sweep as sweep_components
            from .cold_gc import sweep as sweep_receipts

            await sweep_receipts(store, limit=min(limit, 32))
            await sweep_components(store, limit=min(limit, 32))
        # Routes contain bounded metadata rather than conversation payloads. Rotate the
        # start so an unfiltered worker cannot starve a busy route behind another.
        if namespace is not None and bot_id is not None:
            routes = [store.route(IdleConversationKey(namespace, bot_id, 1, 1))]
        else:
            if not store.route_pending:
                page = array(
                    await store.connection.call(
                        "SSCAN", f"{store.prefix}:routes", store.route_scan, "COUNT", 64
                    )
                )
                store.route_scan = text(page[0]) if not isinstance(page[0], int) else str(page[0])
                store.route_pending.extend(array(page[1]))
            routes = [text(item) for item in store.route_pending[:64]]
            del store.route_pending[:64]
            if routes:
                offset = store.route_cursor % len(routes)
                routes = routes[offset:] + routes[:offset]
                store.route_cursor += 1
        claims: list[Claim] = []
        for route in routes:
            due = f"{store.prefix}:due:{route}"
            candidates = array(
                await store.connection.call("ZRANGEBYSCORE", due, "-inf", now, "LIMIT", 0, limit)
            )
            selected: list[IdleConversationKey] = []
            for item in candidates:
                value = decode(text(item))
                if not isinstance(value, IdleConversationKey):
                    raise SchemaUnsupported("Invalid Redis due identity")
                if (namespace is None or namespace == value.namespace) and (
                    bot_id is None or bot_id == value.bot_id
                ):
                    selected.append(value)
            if not selected:
                continue
            selected = selected[: limit - len(claims)]
            eligible: list[IdleConversationKey] = []
            validated_jobs: dict[IdleConversationKey, str] = {}
            for selected_key in selected:
                try:
                    engine, _, _ = await store.read(selected_key)
                except (BackendInconsistent, SchemaUnsupported) as error:
                    await store.quarantine.park(selected_key, reason=type(error).__name__)
                    continue
                if not engine.job():

                    async def restore_job(current: Engine) -> None:
                        await current.reconcile(limit=1)

                    await store.mutate(selected_key, restore_job)
                    continue
                if engine.stale_active():

                    async def disarm(current: Engine) -> None:
                        current.disarm_stale()

                    await store.mutate(selected_key, disarm)
                else:
                    eligible.append(selected_key)
                    validated_jobs[selected_key] = engine.original_job
            selected = eligible
            if not selected:
                continue
            response = array(
                await store.connection.script(
                    CLAIM,
                    [
                        due,
                        *(store.keys(key)[1] for key in selected),
                        store.prefix + ":created",
                        store.prefix + ":config",
                        store.prefix + ":config-established",
                    ],
                    [
                        lease_seconds,
                        secrets.token_urlsafe(24),
                        *(store.member(key) for key in selected),
                        *(validated_jobs[key] for key in selected),
                        store.history,
                    ],
                )
            )
            for i in range(0, len(response), 2):
                key = decode(text(response[i]))
                if not isinstance(key, IdleConversationKey):
                    raise SchemaUnsupported("Invalid Redis claimed identity")
                job = job_decode(text(response[i + 1]))
                claims.append(
                    Claim(key, job.token or "", job.generation, job.lease_until, job.deadline)
                )
            if len(claims) >= limit:
                break
        return claims

    async def _lease(self, claim: Claim, action: str, value: object = "") -> str:
        await self._store.ready()
        keys = self._store.keys(claim.key)
        response = text(
            await self._store.connection.script(
                LEASE,
                [
                    keys[1],
                    keys[2],
                    self._store.prefix + ":created",
                    self._store.prefix + ":config",
                    self._store.prefix + ":config-established",
                ],
                [
                    claim.token,
                    claim.generation,
                    action,
                    value,
                    self._store.member(claim.key),
                    secrets.token_urlsafe(24),
                    self._store.history,
                    self._store.clock.now(),
                ],
            )
        )
        if not response:
            raise OwnershipLost("Redis deadline ownership expired or was replaced")
        return response

    async def renew_claim(self, claim: Claim, *, lease_seconds: float) -> Claim:
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("Lease must be positive")
        job = job_decode(await self._lease(claim, "renew", lease_seconds))
        return Claim(claim.key, claim.token, claim.generation, job.lease_until, job.deadline)

    async def validate_claim(self, claim: Claim) -> None:
        await self._lease(claim, "check")

    async def release_claim(self, claim: Claim, *, retry_at: float | None = None) -> None:
        if retry_at is not None and not math.isfinite(retry_at):
            raise ValueError("Retry time must be finite")

        async def release(engine: Engine) -> None:
            await engine.release_claim(claim, retry_at=retry_at)

        await self._store.mutate(claim.key, release, claim=claim)

    async def reconcile(self, *, limit: int = 100) -> int:
        if isinstance(limit, bool) or limit < 1:
            raise ValueError("Reconciliation limit must be positive")
        store = self._store
        await store.ready()
        store.config_value(await store.raw_config())
        if store.format_version == 3:
            from .canonical_gc import sweep as sweep_components
            from .cold_gc import sweep as sweep_receipts

            await sweep_receipts(store, limit=min(limit, 32))
            await sweep_components(store, limit=min(limit, 32))
        if not store.reconcile_pending:
            response = array(
                await store.connection.call(
                    "SSCAN", f"{store.prefix}:live", store.cursor, "COUNT", limit
                )
            )
            store.cursor = (
                text(response[0]) if not isinstance(response[0], int) else str(response[0])
            )
            store.reconcile_pending.extend(array(response[1]))
        members = store.reconcile_pending[:limit]
        del store.reconcile_pending[:limit]
        repaired = 0
        for member in members:
            key = decode(text(member))
            if not isinstance(key, IdleConversationKey):
                raise SchemaUnsupported("Invalid Redis retained identity")

            if await store.quarantine.contains(key):
                continue

            async def repair(engine: Engine, key: IdleConversationKey = key) -> int:
                engine.disarm_stale()
                record = await engine.load(key)
                manifest = engine.manifest()
                if (
                    record is not None
                    and manifest is not None
                    and not manifest.enabled
                    and record.idle.phase == Phase.ACTIVE
                ):
                    engine._save(replace(record, idle=IdleSnapshot()))  # pyright: ignore[reportPrivateUsage]
                return await engine.reconcile(limit=1)

            try:
                repaired += await store.mutate(key, repair)
            except (BackendInconsistent, SchemaUnsupported) as error:
                await store.quarantine.park(key, reason=type(error).__name__)
        return repaired
