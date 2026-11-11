"""Bounded metadata collection; physical completed payloads expire independently."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from ..errors import BackendInconsistent
from ..models import IdleConversationKey
from .codec import decode
from .cold import keys, receipt_key

# Shared internal Lua preflight is intentionally reused.
# pyright: reportPrivateUsage=false
from .cold_scripts import IDENTITY
from .redis_scripts import _TYPES
from .redis_transport import array, text

if TYPE_CHECKING:
    from .redis_store import RedisStore

_OBSERVE = (
    _TYPES
    + r"""
if not types(KEYS,{'zset','string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT receipt sweep type') end
if not namespace(KEYS[2],ARGV[1],KEYS[3],KEYS[4]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
local tm=redis.call('TIME'); local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
return redis.call('ZRANGEBYSCORE',KEYS[1],'-inf',now,'LIMIT',0,ARGV[2])
"""
)

_COLLECT = (
    IDENTITY
    + _TYPES
    + r"""
local expected={'hash','zset','zset','string','string','string','hash'}
for i=8,#KEYS do expected[i]='string' end
if not types(KEYS,expected) then return redis.error_reply('IDLE_INCONSISTENT receipt sweep type') end
if not namespace(KEYS[4],ARGV[2],KEYS[5],KEYS[6]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if redis.call('HLEN',KEYS[1])~=redis.call('ZCARD',KEYS[2]) then return redis.error_reply('IDLE_INCONSISTENT receipt sweep index count') end
local valid,items=pcall(cjson.decode,ARGV[3])
if not valid or type(items)~='table' or #items~=#KEYS-7 or #items>1000 then return redis.error_reply('IDLE_INCONSISTENT receipt sweep delta') end
local tm=redis.call('TIME'); local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
-- Parked/unknown evidence is an administrative concern, never an automatic GC target.
if redis.call('HEXISTS',KEYS[7],ARGV[1])==1 then
 redis.call('ZADD',KEYS[3],string.format('%.0f',now+60000),ARGV[1]); return 0
end
local seen={}
local remove={}
for i,item in ipairs(items) do
 if type(item)~='table' or not identity(item.id)
  or type(item.key)~='string' or item.key~=KEYS[7+i] or seen[item.id] then
  return redis.error_reply('IDLE_INCONSISTENT receipt sweep identity') end
 seen[item.id]=true
 local member=redis.call('HGET',KEYS[1],item.id)
 local expiry=redis.call('ZSCORE',KEYS[2],item.id)
 if member and member~=item.key then return redis.error_reply('IDLE_INCONSISTENT receipt sweep scope') end
 if (member and not expiry) or (expiry and not member) then return redis.error_reply('IDLE_INCONSISTENT receipt sweep membership') end
 if expiry then
  local stamp=tonumber(expiry)
  if not stamp or stamp~=stamp or stamp<=0 or stamp>9007199254740991 or stamp%1~=0 then
   return redis.error_reply('IDLE_INCONSISTENT receipt sweep expiry') end
  if stamp<=now then
   local raw=redis.call('GET',item.key)
   if raw then
    local ok,row=pcall(cjson.decode,raw)
    if not ok or type(row)~='table' or row.schema_version~=3 or row.key~=ARGV[1]
     or row.operation_id~=item.id or row.expires_at~=stamp then
     return redis.error_reply('IDLE_INCONSISTENT receipt sweep row proof') end
   end
   remove[#remove+1]=item
  end
 end
end
-- Every key/type/identity/expiry check above precedes the first deletion.
for _,item in ipairs(remove) do
 redis.call('DEL',item.key); redis.call('HDEL',KEYS[1],item.id); redis.call('ZREM',KEYS[2],item.id)
end
if redis.call('HLEN',KEYS[1])==0 then
 redis.call('DEL',KEYS[1],KEYS[2]); redis.call('ZREM',KEYS[3],ARGV[1])
else
 local first=redis.call('ZRANGE',KEYS[2],0,0,'WITHSCORES')
 redis.call('ZADD',KEYS[3],first[2],ARGV[1])
end
return #remove
"""
)


async def sweep(store: RedisStore, *, limit: int = 32) -> int:
    """Remove at most ``limit`` expired completed entries, never protected evidence."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Receipt sweep limit must be between 1 and 1000")
    await store.initialize()
    if store.format_version != 3:
        return 0
    members = array(
        await store.connection.script(
            _OBSERVE,
            [
                store.prefix + ":receipt-sweep",
                store.prefix + ":created",
                store.prefix + ":config",
                store.prefix + ":config-established",
            ],
            [store.history, limit],
            mutation=False,
        )
    )
    removed = selected = 0
    for encoded in members:
        member = text(encoded)
        key = decode(member)
        if not isinstance(key, IdleConversationKey) or store.member(key) != member:
            raise BackendInconsistent("Receipt sweep conversation identity changed")
        _, metadata, expiry, _ = keys(store, key)
        # The authoritative Lua check repeats the expiry observation before deletion.
        candidates = array(
            await store.connection.call(
                "ZRANGEBYSCORE",
                expiry,
                "-inf",
                "+inf",
                "LIMIT",
                0,
                limit - selected,
            )
        )
        items: list[dict[str, str]] = []
        for value in candidates:
            operation_id = text(value)
            if not 1 <= len(operation_id) <= 256:
                raise BackendInconsistent("Receipt sweep operation identity changed")
            items.append({"id": operation_id, "key": receipt_key(store, key, operation_id)})
        selected += len(items)
        result = await store.connection.script(
            _COLLECT,
            [
                metadata,
                expiry,
                store.prefix + ":receipt-sweep",
                store.prefix + ":created",
                store.prefix + ":config",
                store.prefix + ":config-established",
                store.prefix + ":parked",
                *(item["key"] for item in items),
            ],
            [member, store.history, json.dumps(items, separators=(",", ":"))],
        )
        removed += int(cast(int, result))
        if selected >= limit:
            break
    return removed
