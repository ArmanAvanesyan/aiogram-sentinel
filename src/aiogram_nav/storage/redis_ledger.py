"""Bounded format-three reads and canonical ledger CAS without snapshot journals."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from ..clock import ManualClock
from ..errors import PersistenceUnavailable
from ..models import ConversationKey
from .ledger import LedgerRead
from .ledger_reducer import NavigationLedgerReducer
from .ledger_scripts import READ
from .redis_transport import array, text

if TYPE_CHECKING:
    from .redis_store import RedisStore


def keys(store: RedisStore, key: ConversationKey) -> list[str]:
    base = store.keys(key)
    record = base[2]
    return [*base, f"{record}:operations", f"{record}:expiry", f"{record}:tokens"]


def _pairs(raw: object) -> dict[str, str]:
    values = array(raw)
    if len(values) % 2:
        raise PersistenceUnavailable("Canonical ledger rows are inconsistent")
    return {text(values[i]): text(values[i + 1]) for i in range(0, len(values), 2)}


async def read(
    store: RedisStore,
    key: ConversationKey,
    *,
    operation_id: str = "",
    token: str = "",
    reservation_id: str = "",
) -> tuple[str, NavigationLedgerReducer]:
    response = array(
        await store.connection.script(
            READ,
            keys(store, key),
            [store.profile, store.history, store.member(key), operation_id, token, reservation_id],
            mutation=False,
        )
    )
    if text(response[0]) != "ok":
        raise PersistenceUnavailable("Canonical ledger history is absent or requires migration")
    hot = text(response[1])
    now = int(text(response[3])) * 1000 + int(text(response[4])) // 1000
    store.clock.update(now)
    rows = _pairs(response[5])
    expiry = {name: int(float(value)) for name, value in _pairs(response[6]).items()}
    revision: str | None = None
    if hot:
        # Strict decoder validates the entire hot/operation contract below.
        body = cast(dict[str, object], json.loads(hot))
        core = cast(dict[str, object], body["core"])
        value = cast(dict[str, object], core["value"])
        fields = cast(dict[str, object], value["value"])
        revision = cast(str, fields["version"])
    snapshot = LedgerRead(
        revision,
        hot or None,
        rows,
        int(response[2]) if type(response[2]) is int else int(text(response[2])),
        expiry,
        tuple(text(value) for value in array(response[7])),
    )
    return hot, NavigationLedgerReducer(key, snapshot, clock=ManualClock(now), config=store.config)
