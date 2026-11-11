"""Explicit bounded SCAN recovery when the retained-membership index is lost."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from ..errors import BackendInconsistent
from ..models import RuntimeSnapshot
from .codec import decode
from .redis_engine import Engine
from .redis_store import RedisStore
from .redis_transport import array, text


@dataclass(frozen=True)
class IndexRecoveryPage:
    cursor: str
    inspected: int
    repaired: int
    pending: int

    @property
    def complete(self) -> bool:
        return self.cursor == "0" and self.pending == 0


class IndexRecovery:
    def __init__(self, store: RedisStore) -> None:
        self.store = store
        self.cursor = "0"
        self.pending: list[object] = []

    async def run(self, *, limit: int = 100) -> IndexRecoveryPage:
        if isinstance(limit, bool) or not isinstance(cast(object, limit), int) or limit < 1:
            raise ValueError("Administrative recovery limit must be a positive integer")
        store = self.store
        await store.ready()
        if not self.pending:
            response = array(
                await store.connection.call(
                    "SCAN",
                    self.cursor,
                    "MATCH",
                    f"{_glob_escape(store.prefix)}:record:*",
                    "COUNT",
                    limit,
                )
            )
            self.cursor = str(response[0]) if isinstance(response[0], int) else text(response[0])
            self.pending.extend(array(response[1]))
        selected, self.pending = self.pending[:limit], self.pending[limit:]
        repaired = 0
        for item in selected:
            record_key = text(item)
            raw = await store.connection.call("GET", record_key)
            if raw is None:
                continue  # Concurrent retention pruning is harmless.
            if store.format_version == 3:
                from .wire_json import strict

                hot = strict(text(raw))
                if (
                    set(hot) != {"schema_version", "kind", "pending_ref", "state"}
                    or hot.get("schema_version") != 3
                    or hot.get("kind") != "idle-hot"
                    or not isinstance(hot.get("state"), str)
                ):
                    raise BackendInconsistent("Invalid authoritative cold Redis envelope")
                value = decode(cast(str, hot["state"]))
            else:
                value = decode(text(raw))
            if not isinstance(value, dict):
                raise BackendInconsistent("Invalid authoritative Redis envelope")
            record = cast("dict[str, object]", value).get("record")
            if not isinstance(record, RuntimeSnapshot) or store.keys(record.key)[0] != record_key:
                raise BackendInconsistent("Administrative record identity mismatch")

            async def repair(engine: Engine) -> None:
                engine.disarm_stale()
                await engine.reconcile(limit=1)

            # The ordinary CAS commit rebuilds live, expiry, route and due indexes;
            # it preserves current claim tokens and does not replay external effects.
            await store.mutate(record.key, repair)
            repaired += 1
        return IndexRecoveryPage(self.cursor, len(selected), repaired, len(self.pending))


def _glob_escape(value: str) -> str:
    return "".join("\\" + char if char in "\\*?[]" else char for char in value)
