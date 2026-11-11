"""Bounded administrative GC of provably orphaned staging metadata, never sources."""

from __future__ import annotations

# Internal Lua namespace/type checks are reused deliberately.
# pyright: reportPrivateUsage=false
import base64
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..errors import BackendInconsistent
from ..models import IdleConversationKey
from .codec import decode
from .cold import keys
from .cold_migration import backup_keys, migration_key
from .redis_scripts import _TYPES
from .redis_transport import array, text
from .wire_json import strict

if TYPE_CHECKING:
    from .redis_store import RedisStore

_COLLECT = (
    _TYPES
    + r"""
if not types(KEYS,{'hash','string','string','string','string','zset','string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT staging sweep key type') end
if not namespace(KEYS[7],ARGV[2],KEYS[8],KEYS[9]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if redis.call('HLEN',KEYS[1])==0 then return 0 end
if redis.call('HLEN',KEYS[1])~=4 or redis.call('HGET',KEYS[1],'key')~=ARGV[1]
 or redis.call('HGET',KEYS[1],'source')~=ARGV[3] then return redis.error_reply('IDLE_INCONSISTENT staging sweep identity') end
local digest=ARGV[3]
local position=tonumber(redis.call('HGET',KEYS[1],'position')); local total=tonumber(redis.call('HGET',KEYS[1],'total'))
if #digest~=64 or string.find(digest,'[^a-f0-9]') or not position or not total or position<0 or position>total
 or position%1~=0 or total%1~=0 or total>9007199254740991 then return redis.error_reply('IDLE_INCONSISTENT staging progress proof') end
local source=redis.call('GET',KEYS[3]); local proof=redis.call('GET',KEYS[4])
if (source and not proof) or (proof and not source) then return redis.error_reply('IDLE_INCONSISTENT staging backup missing') end
-- Any still-retained backup or protected pending body requires explicit inspection.
if source or redis.call('EXISTS',KEYS[5])==1 then return 0 end
local hot=redis.call('GET',KEYS[2])
if hot then
 local ok,state=pcall(cjson.decode,hot)
 if not ok or type(state)~='table' then return redis.error_reply('IDLE_INCONSISTENT staging hot state') end
 if state.kind~='idle-hot' then return 0 end
 if state.schema_version~=3 or state.pending_ref~=cjson.null then return 0 end
end
local tm=redis.call('TIME'); local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
if redis.call('ZCOUNT',KEYS[6],'('..string.format('%.0f',now),'+inf')>0 then return 0 end
redis.call('DEL',KEYS[1]); return 1
"""
)


@dataclass(frozen=True)
class StagingSweepPage:
    cursor: str
    inspected: int
    removed: int


async def sweep_staging(
    store: RedisStore, *, cursor: str = "0", limit: int = 32
) -> StagingSweepPage:
    """Inspect at most ``limit`` staging hashes; leave incomplete/protected work intact."""
    if (
        type(limit) is not int
        or not 1 <= limit <= 1000
        or type(cursor) is not str
        or len(cursor) > 8_388_608
    ):
        raise ValueError("Invalid bounded migration staging cursor/limit")
    await store.initialize()
    pending: list[str] = []
    position = cursor
    if cursor.startswith("page:"):
        try:
            body = strict(base64.urlsafe_b64decode(cursor[5:].encode()).decode())
            raw_cursor, raw_pending = body["cursor"], body["pending"]
            if type(raw_cursor) is not str or not isinstance(raw_pending, list):
                raise ValueError
            if any(type(item) is not str for item in cast(list[object], raw_pending)):
                raise ValueError
            position, pending = raw_cursor, cast(list[str], raw_pending)
        except (ValueError, KeyError, UnicodeDecodeError) as error:
            raise ValueError("Malformed migration staging cursor") from error
    if not position.isdecimal():
        raise ValueError("Malformed migration staging cursor")
    prefix = store.prefix + ":cold-migration:"
    if not pending:
        escaped = "".join("\\" + char if char in "\\*?[]" else char for char in prefix)
        page = array(
            await store.connection.call("SCAN", position, "MATCH", escaped + "*", "COUNT", limit)
        )
        position = str(page[0]) if isinstance(page[0], int) else text(page[0])
        pending = [text(value) for value in array(page[1])]
    selected, pending = pending[:limit], pending[limit:]
    inspected = removed = 0
    for name in selected:
        if not name.startswith(prefix):
            raise ValueError("Migration staging cursor belongs to another namespace")
        values = await store.connection.call("HMGET", name, "key", "source")
        pair = array(values)
        if pair == [None, None]:
            continue
        if len(pair) != 2 or pair[0] is None or pair[1] is None:
            raise BackendInconsistent("Migration staging identity is missing")
        member, digest = text(pair[0]), text(pair[1])
        key = decode(member)
        if not isinstance(key, IdleConversationKey) or migration_key(store, key) != name:
            raise BackendInconsistent("Migration staging scope changed")
        inspected += 1
        backup, proof = backup_keys(store, key)
        result = await store.connection.script(
            _COLLECT,
            [
                name,
                store.keys(key)[0],
                backup,
                proof,
                keys(store, key)[0],
                keys(store, key)[2],
                store.prefix + ":created",
                store.prefix + ":config",
                store.prefix + ":config-established",
            ],
            [member, store.history, digest],
        )
        removed += int(cast(int, result))
    if pending:
        position = (
            "page:"
            + base64.urlsafe_b64encode(
                json.dumps({"cursor": position, "pending": pending}).encode()
            ).decode()
        )
    return StagingSweepPage(position, inspected, removed)
