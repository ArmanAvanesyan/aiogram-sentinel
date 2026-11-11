"""Bounded canonical-ledger GC and an authoritative hot-retirement barrier."""

from __future__ import annotations

# These are backend-owned Lua/identity helpers, deliberately shared without Nav imports.
# pyright: reportPrivateUsage=false
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..errors import BackendInconsistent, Overloaded
from ..models import IdleConversationKey, RuntimeSnapshot
from .canonical import body
from .canonical_redis import component_prefix, keys, row_key
from .codec import decode
from .cold_scripts import IDENTITY
from .redis_scripts import _TYPES
from .redis_transport import array, text
from .wire_json import compact, strict

if TYPE_CHECKING:
    from .redis_store import RedisStore

RETIRE_PREFLIGHT = r"""
local ok,retire=pcall(cjson.decode,ARGV[17])
if not ok or type(retire)~='table' or retire.kind~='canonical-retirement'
 or retire.key_start~=18+#cold.gc or type(retire.components)~='table' or #retire.components>32
 or #KEYS~=retire.key_start+5*#retire.components then return redis.error_reply('IDLE_INCONSISTENT canonical retirement shape') end
for i=retire.key_start,#KEYS do
 local t=redis.call('TYPE',KEYS[i]).ok
 local offset=(i-retire.key_start)%5
 local expected=({'hash','zset','hash','set','string'})[offset+1]
 if i==#KEYS then expected='zset' end
 if t~='none' and t~=expected then return redis.error_reply('IDLE_INCONSISTENT canonical retirement type') end
end
local retained=false;local latest=0
for i,item in ipairs(retire.components) do
 local first=retire.key_start+5*(i-1)
 if type(item)~='table' or type(item.prefix)~='string' or type(item.component)~='string'
  or KEYS[first]~=item.prefix..':metadata' or KEYS[first+1]~=item.prefix..':expiry'
  or KEYS[first+2]~=item.prefix..':indexes' or KEYS[first+3]~=item.prefix..':protected' or KEYS[first+4]~=item.prefix..':index-count' then
  return redis.error_reply('IDLE_INCONSISTENT canonical retirement scope') end
 local indexcount=redis.call('GET',KEYS[first+4])
 if not indexcount or indexcount~=tostring(redis.call('HLEN',KEYS[first+2])) then return redis.error_reply('IDLE_INCONSISTENT canonical retirement index count') end
 local protected=redis.call('SCARD',KEYS[first+3]);local terminal=redis.call('ZCARD',KEYS[first+1])
 if redis.call('HLEN',KEYS[first])~=protected+terminal then return redis.error_reply('IDLE_INCONSISTENT canonical retirement membership') end
 if protected>0 then retained=true end
 local earliest=redis.call('ZRANGE',KEYS[first+1],0,0,'WITHSCORES')
 if #earliest>0 then
  local value=tonumber(earliest[2])
  if not value or value~=value or value<=0 or value%1~=0 or value>9007199254740991 then return redis.error_reply('IDLE_INCONSISTENT canonical retirement minimum expiry') end
 end
 local final=redis.call('ZREVRANGE',KEYS[first+1],0,0,'WITHSCORES')
 if #final>0 then
  local expiry=tonumber(final[2])
  if not expiry or expiry~=expiry or expiry<=0 or expiry%1~=0 or expiry>9007199254740991 then return redis.error_reply('IDLE_INCONSISTENT canonical retirement expiry') end
  if expiry>nowms then retained=true end
  latest=math.max(latest,expiry)
 end
 for _,field in ipairs({'current_owner','pending_id'}) do
  local id=item[field]
  if id~=cjson.null then
   if type(id)~='string' or id=='' then return redis.error_reply('IDLE_INCONSISTENT canonical retirement owner') end
   local encoded=redis.call('HGET',KEYS[first],id)
   if not encoded then return redis.error_reply('IDLE_INCONSISTENT canonical retirement owner proof missing') end
   local valid,meta=pcall(cjson.decode,encoded)
   local score=redis.call('ZSCORE',KEYS[first+1],id);local owned=redis.call('SISMEMBER',KEYS[first+3],id)
   if not valid or type(meta)~='table' or meta.key~=item[field..'_key'] then return redis.error_reply('IDLE_INCONSISTENT canonical retirement owner scope') end
   if meta.status=='protected' then
    if score or owned~=1 then return redis.error_reply('IDLE_INCONSISTENT canonical retirement protected proof') end
   elseif meta.status=='terminal' then
    if not score or owned~=0 or field=='pending_id' then return redis.error_reply('IDLE_INCONSISTENT canonical retirement terminal proof') end
    local exact=tonumber(score)
    if not exact or exact~=exact or exact<=0 or exact%1~=0 or exact>9007199254740991 then return redis.error_reply('IDLE_INCONSISTENT canonical retirement owner expiry') end
   else return redis.error_reply('IDLE_INCONSISTENT canonical retirement classification') end
  end
 end
end
if ARGV[2]=='' and retained then
 -- Only the sweep schedule changes, after every cold/domain/fence/type preflight.
 -- Neither session/activity expiry nor any promised replay deadline is extended.
 local deferred=math.max(now+60,latest/1000)
 redis.call('ZADD',KEYS[8],'GT',deferred,ARGV[4])
 return 'canonical_retained'
end
"""

_SELECT = (
    _TYPES
    + r"""
if not types(KEYS,{'zset','string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT component sweep type') end
if not namespace(KEYS[2],ARGV[1],KEYS[3],KEYS[4]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
local tm=redis.call('TIME');local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
return redis.call('ZRANGEBYSCORE',KEYS[1],'-inf',now,'LIMIT',0,ARGV[2])
"""
)

_META = (
    _TYPES
    + r"""
if not types(KEYS,{'string','hash','zset','hash','set','zset','string','string','string','hash','string'}) then return redis.error_reply('IDLE_INCONSISTENT component GC type') end
if not namespace(KEYS[7],ARGV[1],KEYS[8],KEYS[9]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[2] then return {'conflict'} end
local count=redis.call('GET',KEYS[11])
if (ARGV[8]=='1' or redis.call('HLEN',KEYS[2])>0) and (not count or count~=tostring(redis.call('HLEN',KEYS[4]))) then return redis.error_reply('IDLE_INCONSISTENT component GC index count') end
local tm=redis.call('TIME');local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
local candidates=redis.call('ZRANGEBYSCORE',KEYS[3],'-inf',now,'LIMIT',0,tonumber(ARGV[3])+2)
local rows={};local bytes=0
for _,id in ipairs(candidates) do
 if id~=ARGV[4] and id~=ARGV[5] then
  local size=redis.call('HSTRLEN',KEYS[2],id)
  if size==0 then return redis.error_reply('IDLE_INCONSISTENT component GC metadata missing') end
  if size>tonumber(ARGV[6]) then return redis.error_reply('IDLE_INCONSISTENT component GC metadata exceeds bound') end
  if bytes+size>tonumber(ARGV[7]) then break end
  bytes=bytes+size
  table.insert(rows,id);table.insert(rows,redis.call('HGET',KEYS[2],id))
  if #rows>=2*tonumber(ARGV[3]) then break end
 end
end
return {'ok',rows,tm[1],tm[2]}
"""
)

_COLLECT = (
    IDENTITY
    + _TYPES
    + r"""
local expected={'string','hash','zset','hash','set','zset','string','string','string','hash','string'}
for i=12,#KEYS do expected[i]='string' end
if not types(KEYS,expected) then return redis.error_reply('IDLE_INCONSISTENT component GC type') end
if not namespace(KEYS[7],ARGV[1],KEYS[8],KEYS[9]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[2] then return {'conflict',0} end
local ok,request=pcall(cjson.decode,ARGV[3])
if not ok or type(request)~='table' or type(request.rows)~='table' or #request.rows>1000
 or #KEYS~=11+#request.rows then return redis.error_reply('IDLE_INCONSISTENT component GC request') end
if type(request.index_limit)~='number' or request.index_limit%1~=0 or request.index_limit<1 or request.index_limit>8192
 or type(request.row_keys)~='table' or type(request.key)~='string' or type(request.member)~='string' then return redis.error_reply('IDLE_INCONSISTENT component GC budget') end
local indexcount=redis.call('GET',KEYS[11])
if (request.identity~=cjson.null or redis.call('HLEN',KEYS[2])>0) and (not indexcount or indexcount~=tostring(redis.call('HLEN',KEYS[4]))) then return redis.error_reply('IDLE_INCONSISTENT component GC index count') end
local protected=redis.call('SCARD',KEYS[5]);local terminal=redis.call('ZCARD',KEYS[3])
if redis.call('HLEN',KEYS[2])~=protected+terminal then return redis.error_reply('IDLE_INCONSISTENT component GC membership') end
local tm=redis.call('TIME');local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
local parked=redis.call('HEXISTS',KEYS[10],request.key)==1
local plans={};local fields=0
for i,item in ipairs(request.rows) do
 if type(item)~='table' or not identity(item.id) or type(item.metadata)~='string'
  or KEYS[11+i]~=item.row_key or item.row_key~=request.row_keys[item.id]
  or item.id==request.current_owner or item.id==request.pending_id then return redis.error_reply('IDLE_INCONSISTENT component GC row scope') end
 if redis.call('HGET',KEYS[2],item.id)~=item.metadata then return {'conflict',0} end
 local score=redis.call('ZSCORE',KEYS[3],item.id)
 if not score or redis.call('SISMEMBER',KEYS[5],item.id)==1 then return redis.error_reply('IDLE_INCONSISTENT component GC protected row') end
 local expiry=tonumber(score)
 if not expiry or expiry~=expiry or expiry<=0 or expiry%1~=0 or expiry>9007199254740991 then return redis.error_reply('IDLE_INCONSISTENT component GC expiry') end
 if expiry>now then return {'conflict',0} end
 local valid,meta=pcall(cjson.decode,item.metadata)
 if not valid or not cold_fields(meta,{key=true,status=true,index_fields=true},3)
  or meta.key~=item.row_key or meta.status~='terminal' or type(meta.index_fields)~='table' then return redis.error_reply('IDLE_INCONSISTENT component GC metadata') end
 local raw=redis.call('GET',item.row_key)
 if raw then
  local good,row=pcall(cjson.decode,raw)
  if not good or type(row)~='table' or row.schema_version~=3 or row.kind~='operation'
   or row.id~=item.id or (row.status~='completed' and row.status~='failed')
   or (request.identity~=cjson.null and row.conversation~=request.identity) then return redis.error_reply('IDLE_INCONSISTENT component GC identity') end
 end
 local count=math.min(#meta.index_fields,tonumber(request.index_limit)-fields)
 if count<0 then return redis.error_reply('IDLE_INCONSISTENT component GC index budget') end
 local chosen={};local remaining={}
 for n,field in ipairs(meta.index_fields) do
  if type(field)~='string' or field=='' or #field>1032 then return redis.error_reply('IDLE_INCONSISTENT component GC index proof') end
  if n<=count then table.insert(chosen,field) else table.insert(remaining,field) end
 end
 fields=fields+count
 local replacement=false
 if #remaining>0 then meta.index_fields=remaining;replacement=cjson.encode(meta) end
 table.insert(plans,{id=item.id,key=item.row_key,fields=chosen,replacement=replacement})
end
for _,field in ipairs({'current_owner','pending_id'}) do
 local id=request[field]
 if id~=cjson.null then
  if not identity(id) then return redis.error_reply('IDLE_INCONSISTENT component GC owner identity') end
  local encoded=redis.call('HGET',KEYS[2],id)
  local valid,meta=pcall(cjson.decode,encoded or '')
  local score=redis.call('ZSCORE',KEYS[3],id);local owned=redis.call('SISMEMBER',KEYS[5],id)
  if not valid or not cold_fields(meta,{key=true,status=true,index_fields=true},3) or meta.key~=request[field..'_key'] or type(meta.index_fields)~='table' then return redis.error_reply('IDLE_INCONSISTENT component GC owner proof') end
  if meta.status=='protected' then
   if score or owned~=1 then return redis.error_reply('IDLE_INCONSISTENT component GC protected owner') end
  elseif meta.status=='terminal' then
   local expiry=tonumber(score)
   if field=='pending_id' or owned~=0 or not expiry or expiry~=expiry or expiry<=0 or expiry%1~=0 or expiry>9007199254740991 then return redis.error_reply('IDLE_INCONSISTENT component GC terminal owner') end
  else return redis.error_reply('IDLE_INCONSISTENT component GC owner classification') end
 end
end
local latest=redis.call('ZREVRANGE',KEYS[3],0,0,'WITHSCORES')
local finalexpiry=#latest>0 and tonumber(latest[2]) or 0
if not finalexpiry or finalexpiry~=finalexpiry or finalexpiry%1~=0 or finalexpiry<0 or finalexpiry>9007199254740991 then return redis.error_reply('IDLE_INCONSISTENT component GC maximum expiry') end
local future=finalexpiry>now
local orphan=request.identity==cjson.null
if parked or (orphan and (protected>0 or future)) then
 redis.call('ZADD',KEYS[6],string.format('%.0f',now+60000),request.member)
 return {'retained',0}
end
local removed=0
-- All preflight, identity, type and expiry checks precede every deletion.
for _,plan in ipairs(plans) do
 for _,field in ipairs(plan.fields) do
  if redis.call('HGET',KEYS[4],field)==plan.id then redis.call('HDEL',KEYS[4],field) end
 end
 if plan.replacement then redis.call('HSET',KEYS[2],plan.id,plan.replacement)
 else
  redis.call('DEL',plan.key);redis.call('HDEL',KEYS[2],plan.id)
  redis.call('ZREM',KEYS[3],plan.id);redis.call('SREM',KEYS[5],plan.id);removed=removed+1
 end
end
if redis.call('HLEN',KEYS[2])==0 then
 redis.call('DEL',KEYS[2],KEYS[3],KEYS[4],KEYS[5]);redis.call('ZREM',KEYS[6],request.member)
 if request.identity==cjson.null then redis.call('DEL',KEYS[11]) else redis.call('SET',KEYS[11],'0') end
else
 redis.call('SET',KEYS[11],tostring(redis.call('HLEN',KEYS[4])))
 local first=redis.call('ZRANGE',KEYS[3],0,0,'WITHSCORES')
 if #first>0 then
  local next=tonumber(first[2]);if next<=now then next=now+60000 end
  redis.call('ZADD',KEYS[6],string.format('%.0f',next),request.member)
 else redis.call('ZREM',KEYS[6],request.member) end
end
return {'ok',removed,#plans,fields}
"""
)


def retirement_payload(
    store: RedisStore, before: RuntimeSnapshot | None, *, cold_key_count: int
) -> tuple[list[str], str] | None:
    """Build a metadata-only guard; its retained response only defers housekeeping."""
    if before is None:
        return None
    descriptors: list[dict[str, object]] = []
    suffix: list[str] = []
    for component, value in before.components.items():
        if not isinstance(value, Mapping) or value.get("canonical") is not True:
            continue
        if len(descriptors) >= 32:
            raise Overloaded(
                "Canonical retirement component budget exceeded", reason="batch", limit=32
            )
        _, hot, _ = body(before, component)
        state = strict(hot) if hot else {}
        prefix = component_prefix(store, before.key, component)
        descriptor: dict[str, object] = {"component": component, "prefix": prefix}
        for field in ("current_owner", "pending_id"):
            owner = state.get(field)
            if owner is not None and (not isinstance(owner, str) or not owner):
                raise BackendInconsistent("Canonical retirement owner is malformed")
            descriptor[field] = owner
            descriptor[field + "_key"] = row_key(prefix, owner) if isinstance(owner, str) else None
        descriptors.append(descriptor)
        suffix.extend(
            [
                prefix + ending
                for ending in (":metadata", ":expiry", ":indexes", ":protected", ":index-count")
            ]
        )
    if not descriptors:
        return None
    if len(descriptors) > 32:
        raise Overloaded("Canonical retirement component budget exceeded", reason="batch", limit=32)
    suffix.append(store.prefix + ":component-sweep")
    return suffix, compact(
        {
            "kind": "canonical-retirement",
            "key_start": 12 + cold_key_count,
            "components": descriptors,
        }
    )


_DEFER = (
    _TYPES
    + r"""
if not types(KEYS,{'zset','string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT component deferral type') end
if not namespace(KEYS[2],ARGV[1],KEYS[3],KEYS[4]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
local tm=redis.call('TIME');local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
redis.call('ZADD',KEYS[1],'XX','GT',string.format('%.0f',now+60000),ARGV[2]);return 0
"""
)


@dataclass(frozen=True)
class _Progress:
    removed: int = 0
    processed: int = 0
    fields: int = 0
    bytes: int = 0


async def _scope(
    store: RedisStore,
    key: IdleConversationKey,
    component: str,
    member: str,
    *,
    limit: int,
    index_limit: int,
    byte_limit: int,
) -> _Progress:
    if await store.quarantine.contains(key):
        await store.connection.script(
            _DEFER,
            [
                store.prefix + ":component-sweep",
                store.prefix + ":created",
                store.prefix + ":config",
                store.prefix + ":config-established",
            ],
            [store.history, member],
        )
        return _Progress()
    engine, raw, _ = await store.read(key)
    record = engine._records.get(key)
    value = record.components.get(component) if record else None
    _, hot, identity = (
        body(record, component)
        if isinstance(value, Mapping) and value.get("canonical") is True
        else (None, None, None)
    )
    header = strict(hot) if hot else {}
    owner, pending = header.get("current_owner"), header.get("pending_id")
    for pointer in (owner, pending):
        if pointer is not None and (not isinstance(pointer, str) or not pointer):
            raise BackendInconsistent("Component GC owner is malformed")
    prefix = component_prefix(store, key, component)
    base = keys(store, key, component)
    wirekeys = [
        base[0],
        base[5],
        base[6],
        base[7],
        base[8],
        store.prefix + ":component-sweep",
        base[1],
        base[2],
        base[3],
        base[4],
        prefix + ":index-count",
    ]
    observed = array(
        await store.connection.script(
            _META,
            wirekeys,
            [
                store.history,
                raw,
                limit,
                owner or "",
                pending or "",
                store.config.max_components_bytes,
                byte_limit,
                "1" if identity is not None else "0",
            ],
            mutation=False,
        )
    )
    if text(observed[0]) == "conflict":
        return _Progress()
    rows = array(observed[1])
    descriptors: list[dict[str, str]] = []
    rowkeys: dict[str, str] = {}
    for index in range(0, len(rows), 2):
        name, encoded = text(rows[index]), text(rows[index + 1])
        expected = row_key(prefix, name)
        metadata = strict(encoded)
        fields = metadata.get("index_fields")
        if (
            set(metadata) != {"key", "status", "index_fields"}
            or metadata["key"] != expected
            or metadata["status"] != "terminal"
            or not isinstance(fields, list)
            or any(
                not isinstance(field, str) or not field or len(field) > 258
                for field in cast(list[object], fields)
            )
        ):
            raise BackendInconsistent("Component GC reverse-index proof changed")
        descriptors.append({"id": name, "metadata": encoded, "row_key": expected})
        rowkeys[name] = expected
    request = compact(
        {
            "rows": descriptors,
            "row_keys": rowkeys,
            "key": store.member(key),
            "member": member,
            "identity": identity,
            "current_owner": owner,
            "pending_id": pending,
            "current_owner_key": row_key(prefix, owner) if isinstance(owner, str) else None,
            "pending_id_key": row_key(prefix, pending) if isinstance(pending, str) else None,
            "index_limit": index_limit,
        }
    )
    response = array(
        await store.connection.script(
            _COLLECT,
            [*wirekeys, *(item["row_key"] for item in descriptors)],
            [store.history, raw, request],
        )
    )
    return _Progress(
        int(cast(int, response[1])),
        int(cast(int, response[2])) if len(response) > 2 else len(descriptors),
        int(cast(int, response[3])) if len(response) > 3 else 0,
        sum(len(item["metadata"].encode()) for item in descriptors),
    )


async def sweep(store: RedisStore, *, limit: int = 32, index_limit: int = 256) -> int:
    """Bound global row, reverse-field and metadata-byte work across all scopes."""
    if (
        type(limit) is not int
        or not 1 <= limit <= 1000
        or type(index_limit) is not int
        or not 1 <= index_limit <= 8192
    ):
        raise ValueError("Invalid bounded canonical GC budgets")
    await store.initialize()
    if store.format_version != 3:
        return 0
    members = array(
        await store.connection.script(
            _SELECT,
            [
                store.prefix + ":component-sweep",
                store.prefix + ":created",
                store.prefix + ":config",
                store.prefix + ":config-established",
            ],
            [store.history, limit],
            mutation=False,
        )
    )
    removed = processed = fields = byte_count = 0
    for item in members:
        member = text(item)
        value = strict(member)
        encoded_key = value.get("key")
        if not isinstance(encoded_key, str):
            raise BackendInconsistent("Component sweep conversation proof changed")
        key = decode(encoded_key)
        component = value.get("component")
        if (
            set(value) != {"key", "component"}
            or not isinstance(key, IdleConversationKey)
            or not isinstance(component, str)
            or not component
            or len(component) > 128
        ):
            raise BackendInconsistent("Component sweep identity changed")
        progress = await _scope(
            store,
            key,
            component,
            member,
            limit=limit - processed,
            index_limit=index_limit - fields,
            byte_limit=store.config.max_components_bytes - byte_count,
        )
        removed += progress.removed
        processed += progress.processed
        fields += progress.fields
        byte_count += progress.bytes
        if (
            processed >= limit
            or fields >= index_limit
            or byte_count >= store.config.max_components_bytes
        ):
            break
    return removed
