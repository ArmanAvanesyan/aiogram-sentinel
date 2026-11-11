"""Conservative per-conversation quarantine preserving unknown schema evidence."""

from __future__ import annotations

import logging
from typing import cast

from ..errors import BackendInconsistent, SchemaUnsupported, VersionConflict
from ..models import IdleConversationKey
from .codec import decode
from .redis_scripts import PARK
from .redis_transport import array, text

_LOG = logging.getLogger(__name__)


class Quarantine:
    def __init__(self, store: object) -> None:
        from .redis_store import RedisStore

        self.store = cast(RedisStore, store)

    async def contains(self, key: IdleConversationKey) -> bool:
        return bool(
            await self.store.connection.call(
                "HEXISTS", self.store.prefix + ":parked", self.store.member(key)
            )
        )

    async def park(self, key: IdleConversationKey, *, reason: str) -> None:
        store = self.store
        now = await store.ready()
        keys = store.keys(key)
        values = array(await store.connection.call("MGET", keys[0], keys[1]))
        previous = [value if value is not None else "" for value in values]
        if await self.contains(key):
            return
        # Classify exactly the snapshot fenced by PARK, not the earlier failing
        # read: another writer/operator may already have repaired that record.
        config = await store.raw_config()
        manifest = store.config_value(config)  # Namespace errors are not per-key corruption.
        from .redis_engine import Engine

        try:
            raw, job = text(previous[0]), text(previous[1])
            if not raw and (
                previous[1] or await store.connection.call("SISMEMBER", keys[3], store.member(key))
            ):
                raise BackendInconsistent("Retained runtime is missing")
            if store.format_version == 3:
                # Classify the supported hot/cold envelope, including protected
                # pending evidence. A repaired snapshot must never be parked by
                # a delayed failure from its predecessor. PARK still CAS-checks
                # the exact hot/job bytes observed above.
                await store.read(key, allow_parked=True)
            else:
                Engine(
                    key=key,
                    raw=raw,
                    job=job,
                    manifest=manifest,
                    now=now,
                    config=store.config,
                    created_at=store.created_at,
                    disarm_epoch=cast(str, store.config_envelope(config)["disarm_epoch"])
                    if config
                    else "",
                )
        except (BackendInconsistent, SchemaUnsupported):
            pass
        else:
            return
        result = await store.connection.script(
            PARK,
            [
                keys[0],
                keys[1],
                keys[2],
                store.prefix + ":parked",
                store.prefix + ":routes",
                store.prefix + ":created",
                store.prefix + ":config",
                store.prefix + ":config-established",
            ],
            [*previous, store.member(key), reason, "park", "", store.route(key), store.history],
        )
        if result == 1:
            _LOG.warning("idle Redis conversation parked; reason=%s", reason)

    async def inspect(
        self, *, cursor: int = 0, limit: int = 100
    ) -> tuple[int, dict[IdleConversationKey, str]]:
        if cursor < 0 or limit < 1:
            raise ValueError("Quarantine cursor and limit must be nonnegative/positive")
        await self.store.ready()
        page = array(
            await self.store.connection.call(
                "HSCAN", self.store.prefix + ":parked", cursor, "COUNT", limit
            )
        )
        # redis-py parses the HSCAN second element into a dictionary.
        values = page[1]
        if isinstance(values, dict):
            pairs = list(cast("dict[object, object]", values).items())
        else:
            items = array(values)
            pairs = list(zip(items[::2], items[1::2], strict=True))
        result: dict[IdleConversationKey, str] = {}
        for member, reason in pairs:
            key = decode(text(member))
            if not isinstance(key, IdleConversationKey):
                raise BackendInconsistent("Invalid Redis quarantine identity")
            result[key] = text(reason)
        return int(str(page[0]) if isinstance(page[0], int) else text(page[0])), result

    async def release(self, key: IdleConversationKey) -> None:
        store = self.store
        engine, raw, _ = await store.read(key, allow_parked=True)
        job = engine.job()
        # The full envelope and job have now passed the current supported codec.
        keys = store.keys(key)
        from .redis_engine import job_decode

        deadline = job_decode(job).eligible_at if job else ""
        result = await store.connection.script(
            PARK,
            [
                keys[0],
                keys[1],
                keys[2],
                store.prefix + ":parked",
                store.prefix + ":routes",
                store.prefix + ":created",
                store.prefix + ":config",
                store.prefix + ":config-established",
            ],
            [
                raw,
                engine.original_job,
                store.member(key),
                "",
                "release",
                deadline,
                store.route(key),
                store.history,
            ],
        )
        if result != 1:
            raise VersionConflict("Redis quarantine release lost a concurrent mutation")
