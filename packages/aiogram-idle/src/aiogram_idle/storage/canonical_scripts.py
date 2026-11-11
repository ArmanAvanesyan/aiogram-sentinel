"""Opaque component observation. Payload keys are proven before fetching rows."""

META = r"""
local function types()
 local expected={'string','string','string','string','hash','hash','zset','hash','set','string'}
 for i,key in ipairs(KEYS) do local actual=redis.call('TYPE',key).ok
  if actual~='none' and actual~=expected[i] then return false end end
 return true
end
if not types() then return redis.error_reply('IDLE_INCONSISTENT canonical key type') end
if redis.call('GET',KEYS[2])~=ARGV[2] or (redis.call('EXISTS',KEYS[4])==1 and redis.call('EXISTS',KEYS[3])==0) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[1] or (redis.call('GET',KEYS[3]) or '')~=ARGV[3] then return {'conflict'} end
if redis.call('HEXISTS',KEYS[5],ARGV[4])==1 then return redis.error_reply('IDLE_INCONSISTENT parked component') end
if ARGV[5]~='' and redis.call('GET',KEYS[10])~=tostring(redis.call('HLEN',KEYS[8])) then return redis.error_reply('IDLE_INCONSISTENT canonical index witness') end
local tm=redis.call('TIME'); local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
local wanted={};local ids={};local required={};local pending={}
local function add(id,proof)
 if id and id~=cjson.null and id~='' then
  if type(id)~='string' then error('IDLE_INCONSISTENT canonical owner') end
  if not wanted[id] then wanted[id]=true;table.insert(ids,id) end
  if proof then required[id]=true end
 end
end
add(ARGV[6],false)
for _,id in ipairs(cjson.decode(ARGV[10])) do add(id,false) end
if ARGV[5]~='' then
 local ok,hot=pcall(cjson.decode,ARGV[5])
 if not ok or type(hot)~='table' then return redis.error_reply('IDLE_INCONSISTENT canonical hot header') end
 add(hot.current_owner,true);add(hot.pending_id,true)
 if hot.pending_id and hot.pending_id~=cjson.null then pending[hot.pending_id]=true end
end
if ARGV[7]~='' then add(redis.call('HGET',KEYS[8],'t:'..ARGV[7]),true) end
if ARGV[8]~='' then add(redis.call('HGET',KEYS[8],'o:'..ARGV[8]),true) end
local indexes={}
for _,field in ipairs(cjson.decode(ARGV[11])) do local owner=redis.call('HGET',KEYS[8],field);add(owner,true);table.insert(indexes,field);table.insert(indexes,owner or '') end
local expired=redis.call('ZRANGEBYSCORE',KEYS[7],'-inf',now,'LIMIT',0,32)
local expired_set={};for _,id in ipairs(expired) do expired_set[id]=true end
for _,id in ipairs(expired) do add(id,false) end
local metadata={};local expiry={}
for _,id in ipairs(ids) do
 local raw=redis.call('HGET',KEYS[6],id)
 local score=redis.call('ZSCORE',KEYS[7],id)
 if score and (not tonumber(score) or tonumber(score)%1~=0 or tonumber(score)<0 or tonumber(score)>9007199254740991) then return redis.error_reply('IDLE_INCONSISTENT canonical expiry value') end
 if not raw and required[id] then return redis.error_reply('IDLE_INCONSISTENT missing canonical owner') end
 if raw then
  local ok,meta=pcall(cjson.decode,raw)
  if not ok or type(meta)~='table' or type(meta.key)~='string' then return redis.error_reply('IDLE_INCONSISTENT canonical metadata') end
  local suffix=string.sub(meta.key,#ARGV[9]+1)
  if string.sub(meta.key,1,#ARGV[9])~=ARGV[9] or #suffix~=64 or string.find(suffix,'[^a-f0-9]') then return redis.error_reply('IDLE_INCONSISTENT canonical row scope') end
  if meta.status=='terminal' then
   if not score or pending[id] or redis.call('SISMEMBER',KEYS[9],id)==1 then return redis.error_reply('IDLE_INCONSISTENT terminal expiry') end
  elseif meta.status=='protected' then
   if score or redis.call('SISMEMBER',KEYS[9],id)~=1 then return redis.error_reply('IDLE_INCONSISTENT protected expiry') end
  else return redis.error_reply('IDLE_INCONSISTENT canonical status') end
  table.insert(metadata,id);table.insert(metadata,raw)
  if score then table.insert(expiry,id);table.insert(expiry,score) end
  if score and tonumber(score)<=now and not expired_set[id] then expired_set[id]=true;table.insert(expired,id) end
 end
end
return {'ok',tm[1],tm[2],redis.call('HLEN',KEYS[6]),metadata,expiry,expired,indexes}
"""

ROWS = r"""
local expected={'string','string','string','string','hash','hash','zset','hash','set','string'}
for i,key in ipairs(KEYS) do local t=redis.call('TYPE',key).ok
 if t~='none' and t~=(expected[i] or 'string') then return redis.error_reply('IDLE_INCONSISTENT canonical row key type') end end
if redis.call('GET',KEYS[2])~=ARGV[2] or (redis.call('EXISTS',KEYS[4])==1 and redis.call('EXISTS',KEYS[3])==0) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[1] or (redis.call('GET',KEYS[3]) or '')~=ARGV[3] then return {'conflict'} end
if redis.call('HEXISTS',KEYS[5],ARGV[4])==1 then return redis.error_reply('IDLE_INCONSISTENT parked component') end
if redis.call('EXISTS',KEYS[6])==1 and redis.call('GET',KEYS[10])~=tostring(redis.call('HLEN',KEYS[8])) then return redis.error_reply('IDLE_INCONSISTENT canonical index witness') end
local descriptors=cjson.decode(ARGV[5]);if #descriptors~=#KEYS-10 then return redis.error_reply('IDLE_INCONSISTENT canonical key count') end
local tm=redis.call('TIME');local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
local rows={}
for i,item in ipairs(descriptors) do
 if redis.call('HGET',KEYS[6],item.id)~=item.metadata then return {'conflict'} end
 local raw=redis.call('GET',KEYS[10+i])
 local expiry=redis.call('ZSCORE',KEYS[7],item.id)
 if not raw and (not expiry or tonumber(expiry)>now) then return redis.error_reply('IDLE_INCONSISTENT promised canonical row missing') end
 if raw and (not expiry or tonumber(expiry)>now) then
  table.insert(rows,item.id);table.insert(rows,raw)
 end
end
return {'ok',rows,tm[1],tm[2]}
"""

PREFLIGHT = r"""
local canonical=cjson.decode(ARGV[17])
local start=canonical.key_start
if type(start)~='number' or start%1~=0 or start~=18+#cold.gc or type(canonical.identity)~='string'
 or type(canonical.delta)~='table' or type(canonical.row_keys)~='table'
 or type(canonical.metadata)~='table' or type(canonical.expected_rows)~='table' or type(canonical.member)~='string' then return redis.error_reply('IDLE_INCONSISTENT canonical delta shape') end
local d=canonical.delta
local expectations={'hash','zset','hash','set','zset','string'}
for i=start,#KEYS do
 local t=redis.call('TYPE',KEYS[i]).ok
 if t~='none' and t~=(expectations[i-start+1] or 'string') then return redis.error_reply('IDLE_INCONSISTENT canonical suffix key type') end
end
if d.expected_revision~=cjson.null and redis.call('GET',KEYS[start+5])~=tostring(redis.call('HLEN',KEYS[start+2])) then return redis.error_reply('IDLE_INCONSISTENT canonical index witness') end
local function mapping(value,kind)
 if type(value)~='table' then return false end
 for key,item in pairs(value) do if type(key)~='string' or key=='' or type(item)~=kind then return false end end
 return true
end
local function sequence(value)
 if type(value)~='table' then return false end
 local count=0;local seen={}
 for i,item in pairs(value) do if type(i)~='number' or i%1~=0 or i<1 or type(item)~='string' or item=='' or seen[item] then return false end seen[item]=true;count=count+1 end
 return count==#value
end
if type(d.revision)~='string' or d.revision=='' or not mapping(d.put,'string')
 or not mapping(d.terminal_retention_ms,'number') or not mapping(d.token_index_put,'string')
 or not sequence(d.delete) or not sequence(d.token_index_delete)
 or not mapping(canonical.row_keys,'string') or not mapping(canonical.metadata,'string') then return redis.error_reply('IDLE_INCONSISTENT canonical mutation fields') end
local allids={};local countids=0
for id,_ in pairs(d.put) do allids[id]=true;countids=countids+1 end
for _,id in ipairs(d.delete) do if not allids[id] then allids[id]=true;countids=countids+1 end end
if countids>64 or #KEYS~=start+5+countids then return redis.error_reply('IDLE_INCONSISTENT canonical mutation budget') end
local positions={}
for i=start+6,#KEYS do positions[KEYS[i]]=true end
for id,_ in pairs(allids) do
 local key=canonical.row_keys[id]
 if not key or not positions[key] then return redis.error_reply('IDLE_INCONSISTENT canonical row key') end
 local previous=redis.call('HGET',KEYS[start],id)
 if previous then
  local ok,meta=pcall(cjson.decode,previous)
  if not ok or type(meta)~='table' or meta.key~=key or not sequence(meta.index_fields) then return redis.error_reply('IDLE_INCONSISTENT canonical row metadata') end
  local score=redis.call('ZSCORE',KEYS[start+1],id)
  if score and (not tonumber(score) or tonumber(score)%1~=0 or tonumber(score)<0 or tonumber(score)>9007199254740991) then return redis.error_reply('IDLE_INCONSISTENT canonical expiry value') end
  if meta.status=='protected' then
   if score or redis.call('SISMEMBER',KEYS[start+3],id)~=1 then return redis.error_reply('IDLE_INCONSISTENT protected canonical proof') end
  elseif meta.status=='terminal' then
   if not score or redis.call('SISMEMBER',KEYS[start+3],id)==1 then return redis.error_reply('IDLE_INCONSISTENT terminal canonical proof') end
  else return redis.error_reply('IDLE_INCONSISTENT canonical metadata status') end
  local priorrow=redis.call('GET',key)
  if not priorrow and (not score or tonumber(score)>nowms) then return redis.error_reply('IDLE_INCONSISTENT promised canonical row missing') end
  local expected=canonical.expected_rows[id]
  if expected~=cjson.null and expected~=nil and type(expected)~='string' then return redis.error_reply('IDLE_INCONSISTENT expected canonical row') end
  if expected and expected~=cjson.null and priorrow~=expected then return 'canonical_conflict' end
 end
end
local deleted={};local newcount=redis.call('HLEN',KEYS[start])
for _,id in ipairs(d.delete) do
 local score=redis.call('ZSCORE',KEYS[start+1],id)
 if redis.call('HEXISTS',KEYS[start],id)==1 then
  if not score or tonumber(score)>nowms or redis.call('SISMEMBER',KEYS[start+3],id)==1 then return 'canonical_protected' end
  newcount=newcount-1
 end
 deleted[id]=true
end
local deadlines={}
for id,raw in pairs(d.put) do
 local ok,row=pcall(cjson.decode,raw)
 local okmeta,meta=pcall(cjson.decode,canonical.metadata[id] or '')
 if not ok or type(row)~='table' or row.schema_version~=3 or row.kind~='operation'
  or row.id~=id or row.conversation~=canonical.identity or not okmeta or type(meta)~='table'
  or meta.key~=canonical.row_keys[id] or not sequence(meta.index_fields) then return redis.error_reply('IDLE_INCONSISTENT canonical identity proof') end
 local terminal=row.status=='completed' or row.status=='failed'
 if not terminal and row.status~='prepared' and row.status~='unknown' then return redis.error_reply('IDLE_INCONSISTENT canonical row status') end
 if meta.status~=(terminal and 'terminal' or 'protected') then return redis.error_reply('IDLE_INCONSISTENT canonical classification') end
 local prior=not deleted[id] and redis.call('ZSCORE',KEYS[start+1],id) or false
 local duration=d.terminal_retention_ms[id]
 if terminal then
  if not prior and not duration then return redis.error_reply('IDLE_INCONSISTENT terminal duration missing') end
  if duration and (duration<=0 or duration%1~=0 or duration>9007199254740991-nowms) then return redis.error_reply('IDLE_INCONSISTENT unsafe canonical expiry') end
  deadlines[id]=prior and tonumber(prior) or nowms+duration
  if deadlines[id]<=nowms then return 'canonical_expired' end
 else
  if duration or prior then return redis.error_reply('IDLE_INCONSISTENT protected canonical TTL') end
 end
 if deleted[id] or redis.call('HEXISTS',KEYS[start],id)==0 then newcount=newcount+1 end
end
for id,_ in pairs(d.terminal_retention_ms) do if not d.put[id] then return redis.error_reply('IDLE_INCONSISTENT orphan canonical retention') end end
if newcount>tonumber(ARGV[16]) then return 'canonical_capacity' end
for index,owner in pairs(d.token_index_put) do
 if #index>1032 or #owner>1024 then return redis.error_reply('IDLE_INCONSISTENT canonical token owner') end
 if not d.put[owner] then
  if redis.call('HGET',KEYS[start+2],index)~=owner then return redis.error_reply('IDLE_INCONSISTENT new index without canonical owner update') end
  local raw=redis.call('HGET',KEYS[start],owner)
  local ok,meta=pcall(cjson.decode,raw or '')
  if not ok or type(meta)~='table' or not sequence(meta.index_fields) then return redis.error_reply('IDLE_INCONSISTENT canonical reverse proof') end
  local found=false
  for _,field in ipairs(meta.index_fields) do if field==index then found=true end end
  if not found then return redis.error_reply('IDLE_INCONSISTENT orphan canonical index') end
 end
end
"""

APPLY = r"""
for _,id in ipairs(d.delete) do
 local previous=redis.call('HGET',KEYS[start],id)
 if previous then
  local meta=cjson.decode(previous)
  for _,field in ipairs(meta.index_fields) do
   if redis.call('HGET',KEYS[start+2],field)==id then redis.call('HDEL',KEYS[start+2],field) end
  end
 end
 redis.call('DEL',canonical.row_keys[id]);redis.call('HDEL',KEYS[start],id)
 redis.call('ZREM',KEYS[start+1],id);redis.call('SREM',KEYS[start+3],id)
end
for id,raw in pairs(d.put) do
 if deadlines[id] then
  redis.call('SET',canonical.row_keys[id],raw,'PXAT',deadlines[id])
  redis.call('ZADD',KEYS[start+1],deadlines[id],id);redis.call('SREM',KEYS[start+3],id)
 else
  redis.call('SET',canonical.row_keys[id],raw);redis.call('PERSIST',canonical.row_keys[id])
  redis.call('ZREM',KEYS[start+1],id);redis.call('SADD',KEYS[start+3],id)
 end
 redis.call('HSET',KEYS[start],id,canonical.metadata[id])
end
for _,index in ipairs(d.token_index_delete) do
 local owner=redis.call('HGET',KEYS[start+2],index)
 if owner and deleted[owner] and not d.put[owner] then redis.call('HDEL',KEYS[start+2],index) end
end
for index,owner in pairs(d.token_index_put) do redis.call('HSET',KEYS[start+2],index,owner) end
redis.call('SET',KEYS[start+5],tostring(redis.call('HLEN',KEYS[start+2])))
if redis.call('HLEN',KEYS[start])==0 then
 redis.call('DEL',KEYS[start],KEYS[start+1],KEYS[start+2],KEYS[start+3])
 redis.call('ZREM',KEYS[start+4],canonical.member)
else
 local first=redis.call('ZRANGE',KEYS[start+1],0,0,'WITHSCORES')
 if #first>0 then redis.call('ZADD',KEYS[start+4],first[2],canonical.member)
 else redis.call('ZREM',KEYS[start+4],canonical.member) end
end
"""


def commit_script() -> str:
    from .cold_scripts import compose_commit

    return compose_commit(extra_preflight=PREFLIGHT, extra_apply=APPLY)
