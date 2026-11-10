"""Format-three canonical rows and bounded server-time ledger transactions."""

READ = """
if redis.call('GET',KEYS[1])~=ARGV[1] or redis.call('GET',KEYS[2])~=ARGV[2]
 or redis.call('SISMEMBER',KEYS[4],'!established')~=1 then return {'history'} end
local hot=redis.call('GET',KEYS[3]) or ''
local indexed=redis.call('SISMEMBER',KEYS[4],ARGV[3])
if (hot~='' and indexed==0) or (hot=='' and indexed==1) then return {'history'} end
local t=redis.call('TIME'); local now=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000)
local wanted={}; local required={}; local ids={}
local function add(id) if id and id~='' and not wanted[id] then wanted[id]=true; table.insert(ids,id) end end
add(ARGV[4])
if hot~='' then
 local value=cjson.decode(hot)
 if value.kind~='hot' or value.schema_version~=3 then return {'legacy',hot,t[1],t[2]} end
 add(value.current_owner~=cjson.null and value.current_owner or nil)
 if value.current_owner~=cjson.null and value.current_owner then required[value.current_owner]=true end
 local pending=value.core.value.value.pending_id
 add(pending~=cjson.null and pending or nil)
 if pending~=cjson.null and pending then required[pending]=true end
end
if ARGV[5]~='' then local id=redis.call('HGET',KEYS[7],'t:'..ARGV[5]); add(id); if id then required[id]=true end end
if ARGV[6]~='' then local id=redis.call('HGET',KEYS[7],'o:'..ARGV[6]); add(id); if id then required[id]=true end end
local expired=redis.call('ZRANGEBYSCORE',KEYS[6],'-inf',now,'LIMIT',0,32)
for _,id in ipairs(expired) do add(id); required[id]=true end
local rows={}; local expiry={}
for _,id in ipairs(ids) do
 local raw=redis.call('HGET',KEYS[5],id)
 if not raw and required[id] then return {'history'} end
 if raw then
  table.insert(rows,id); table.insert(rows,raw)
  local score=redis.call('ZSCORE',KEYS[6],id)
  if score then table.insert(expiry,id); table.insert(expiry,score) end
 end
end
return {'ok',hot,redis.call('HLEN',KEYS[5]),t[1],t[2],rows,expiry,expired}
"""

COMMIT = """
if redis.call('GET',KEYS[1])~=ARGV[1] or redis.call('GET',KEYS[2])~=ARGV[2]
 or redis.call('SISMEMBER',KEYS[4],'!established')~=1 then return 'history' end
local raw=redis.call('GET',KEYS[3]) or ''
local indexed=redis.call('SISMEMBER',KEYS[4],ARGV[3])
if (raw~='' and indexed==0) or (raw=='' and indexed==1) then return 'history' end
if raw~=ARGV[4] then return 'retry' end
if ARGV[7]~='' and (redis.call('GET',KEYS[8])~=ARGV[7] or redis.call('PTTL',KEYS[8])<=0) then return 'ownership' end
local t=redis.call('TIME'); local now=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000)
if tonumber(ARGV[8])>0 and now>=tonumber(ARGV[8]) then return 'expired' end
local delta=cjson.decode(ARGV[5])
local function mapping(value,kind)
 if type(value)~='table' then return false end
 for name,item in pairs(value) do
  if type(name)~='string' or name=='' or type(item)~=kind then return false end
 end
 return true
end
local function sequence(value)
 if type(value)~='table' then return false end
 local count=0
 for index,item in pairs(value) do
  if type(index)~='number' or index%1~=0 or index<1 or type(item)~='string' or item=='' then return false end
  count=count+1
 end
 return count==#value
end
if type(delta)~='table' or type(delta.revision)~='string' or delta.revision==''
 or (delta.expected_revision~=cjson.null and type(delta.expected_revision)~='string')
 or (delta.hot~=cjson.null and type(delta.hot)~='string')
 or not mapping(delta.put,'string') or not mapping(delta.terminal_retention_ms,'number')
 or not mapping(delta.token_index_put,'string') or not sequence(delta.delete)
 or not sequence(delta.token_index_delete) then return 'malformed' end
local hot=delta.hot~=cjson.null and delta.hot or ''
if raw=='' and hot~='' and redis.call('SCARD',KEYS[4])-1>=tonumber(ARGV[6]) then return 'capacity' end
for index,kind in pairs({[5]='hash',[6]='zset',[7]='hash'}) do
 local actual=redis.call('TYPE',KEYS[index]).ok
 if actual~='none' and actual~=kind then return 'history' end
end
for _,id in ipairs(delta.delete) do
 local expiry=redis.call('ZSCORE',KEYS[6],id)
 if (not expiry and redis.call('HEXISTS',KEYS[5],id)==1) or (expiry and tonumber(expiry)>now) then return 'protected' end
end
local count=redis.call('HLEN',KEYS[5])
for _,id in ipairs(delta.delete) do if redis.call('HEXISTS',KEYS[5],id)==1 then count=count-1 end end
for id,_ in pairs(delta.put) do if redis.call('HEXISTS',KEYS[5],id)==0 then count=count+1 end end
if count>tonumber(ARGV[9]) then return 'receipts' end
-- All validation precedes writes, including operation/index types and retention.
for id,duration in pairs(delta.terminal_retention_ms) do
 if not delta.put[id] or duration<=0 or duration==math.huge or duration%1~=0 then return 'malformed' end
end
for _,id in ipairs(delta.delete) do
 redis.call('HDEL',KEYS[5],id); redis.call('ZREM',KEYS[6],id)
end
for id,value in pairs(delta.put) do redis.call('HSET',KEYS[5],id,value) end
for id,duration in pairs(delta.terminal_retention_ms) do redis.call('ZADD',KEYS[6],now+tonumber(duration),id) end
local deleted={}
for _,id in ipairs(delta.delete) do deleted[id]=true end
for _,id in ipairs(delta.token_index_delete) do
 local owner=redis.call('HGET',KEYS[7],id)
 if owner and deleted[owner] then redis.call('HDEL',KEYS[7],id) end
end
for id,owner in pairs(delta.token_index_put) do redis.call('HSET',KEYS[7],id,owner) end
if hot=='' then
 redis.call('DEL',KEYS[3],KEYS[5],KEYS[6],KEYS[7]); redis.call('SREM',KEYS[4],ARGV[3])
else
 redis.call('SET',KEYS[3],hot); redis.call('SADD',KEYS[4],ARGV[3])
end
return 'ok'
"""
