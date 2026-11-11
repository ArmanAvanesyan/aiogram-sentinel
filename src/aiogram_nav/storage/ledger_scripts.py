"""Redis 7 canonical per-operation STRING receipts, physical TTL and bounded indexes."""

READ = """
if redis.call('GET',KEYS[1])~=ARGV[1] or redis.call('GET',KEYS[2])~=ARGV[2]
 or redis.call('SISMEMBER',KEYS[4],'!established')~=1 then return {'history'} end
local hot=redis.call('GET',KEYS[3]) or ''
local indexed=redis.call('SISMEMBER',KEYS[4],ARGV[3])
if (hot~='' and indexed==0) or (hot=='' and indexed==1) then return {'history'} end
local t=redis.call('TIME'); local now=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000)
local count_type=redis.call('TYPE',KEYS[9]).ok
if count_type~='none' and count_type~='string' then return {'history'} end
local index_count=redis.call('GET',KEYS[9])
local function valid_count(value)
 return type(value)=='string' and string.match(value,'^%d+$') and (#value==1 or string.sub(value,1,1)~='0') and tonumber(value)==redis.call('HLEN',KEYS[7])
end
if hot=='' and (index_count or redis.call('HLEN',KEYS[5])~=0 or redis.call('HLEN',KEYS[7])~=0) then return {'history'} end
local wanted={}; local required={}; local ids={}; local expired={}; local expired_set={}
local function add(id) if id and id~='' and not wanted[id] then wanted[id]=true; table.insert(ids,id) end end
local function expire(id) if not expired_set[id] then expired_set[id]=true; table.insert(expired,id) end end
add(ARGV[4])
if hot~='' then
 local value=cjson.decode(hot)
 if value.schema_version==1 or value.schema_version==2 then
  if index_count or redis.call('HLEN',KEYS[5])~=0 or redis.call('EXISTS',KEYS[6],KEYS[7],KEYS[8])~=0 then return {'history'} end
  return {'legacy',hot,t[1],t[2]}
 end
 if value.kind~='hot' or value.schema_version~=3 then return {'history'} end
 if not valid_count(index_count) then return {'history'} end
 for _,id in ipairs({value.current_owner,value.pending_id}) do
  if id~=cjson.null then add(id); required[id]=true end
 end
end
local fields={ARGV[5]~='' and 't:'..ARGV[5] or '',ARGV[6]~='' and 'o:'..ARGV[6] or ''}
for _,field in ipairs(cjson.decode(ARGV[7] or '[]')) do table.insert(fields,field) end
local proofs={}
for _,field in ipairs(fields) do
 if field~='' then
  local id=redis.call('HGET',KEYS[7],field)
  table.insert(proofs,field); table.insert(proofs,id or '')
  if id then add(id); required[id]=true end
 end
end
for _,id in ipairs(redis.call('ZRANGEBYSCORE',KEYS[6],'-inf',now,'LIMIT',0,32)) do add(id); required[id]=true end
local rows={}; local expiry={}; local metadata={}
for _,id in ipairs(ids) do
 local encoded=redis.call('HGET',KEYS[5],id)
 if not encoded then if required[id] then return {'history'} end
 else
  local meta=cjson.decode(encoded)
  if type(meta.key)~='string' or string.sub(meta.key,1,#KEYS[3]+11)~=KEYS[3]..':operation:' then return {'history'} end
  local score=redis.call('ZSCORE',KEYS[6],id)
  local protected=redis.call('SISMEMBER',KEYS[8],id)
  if meta.status=='terminal' then
   if not score or protected==1 then return {'history'} end
   table.insert(expiry,id); table.insert(expiry,score)
  elseif meta.status~='protected' or score or protected~=1 then return {'history'} end
  table.insert(metadata,id); table.insert(metadata,encoded)
  local raw=redis.call('GET',meta.key)
  if score and tonumber(score)<=now then expire(id)
  elseif not raw then return {'history'}
  else table.insert(rows,id); table.insert(rows,raw) end
 end
end
return {'ok',hot,redis.call('HLEN',KEYS[5]),t[1],t[2],rows,expiry,expired,metadata,proofs}
"""

COMMIT = """
if redis.call('GET',KEYS[1])~=ARGV[1] or redis.call('GET',KEYS[2])~=ARGV[2]
 or redis.call('SISMEMBER',KEYS[4],'!established')~=1 then return 'history' end
local raw=redis.call('GET',KEYS[3]) or ''
local indexed=redis.call('SISMEMBER',KEYS[4],ARGV[3])
if (raw~='' and indexed==0) or (raw=='' and indexed==1) then return 'history' end
if raw~=ARGV[4] then return 'retry' end
if ARGV[7]~='' and (redis.call('GET',KEYS[10])~=ARGV[7] or redis.call('PTTL',KEYS[10])<=0) then return 'ownership' end
local t=redis.call('TIME'); local now=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000)
if tonumber(ARGV[8])>0 and now>=tonumber(ARGV[8]) then return 'expired' end
local delta=cjson.decode(ARGV[5]); local rowkeys=cjson.decode(ARGV[10]); local metas=cjson.decode(ARGV[11])
local migration=cjson.decode(ARGV[12]); local migrating=ARGV[13]~=''
if migrating then
 local manifest=redis.call('GET',KEYS[11])
 if not manifest then return 'history' end
 local proof=cjson.decode(manifest)
 if proof.format~=3 or proof.operation_id~=ARGV[13] then return 'history' end
elseif next(migration)~=nil then return 'malformed' end
local function mapping(value,kind)
 if type(value)~='table' then return false end
 for name,item in pairs(value) do if type(name)~='string' or name=='' or type(item)~=kind then return false end end
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
 or not sequence(delta.token_index_delete) or not mapping(rowkeys,'string') or not mapping(metas,'string') then return 'malformed' end
for index,kind in pairs({[5]='hash',[6]='zset',[7]='hash',[8]='set',[9]='string'}) do
 local actual=redis.call('TYPE',KEYS[index]).ok
 if actual~='none' and actual~=kind then return 'history' end
end
local witness=redis.call('GET',KEYS[9])
if raw=='' or migrating then
 if witness or redis.call('HLEN',KEYS[7])~=0 then return 'history' end
else
 if type(witness)~='string' or not string.match(witness,'^%d+$') or (#witness>1 and string.sub(witness,1,1)=='0') or tonumber(witness)~=redis.call('HLEN',KEYS[7]) then return 'history' end
end
local hot=delta.hot~=cjson.null and delta.hot or ''
if hot~='' then
 local header=cjson.decode(hot)
 if header.kind~='hot' or header.schema_version~=3 or header.revision~=delta.revision
  or type(header.core)~='table' or (header.pending_id~=cjson.null and type(header.pending_id)~='string')
  or (header.current_owner~=cjson.null and type(header.current_owner)~='string')
  or (header.session_id~=cjson.null and type(header.session_id)~='string') then return 'malformed' end
end
if raw=='' and hot~='' and redis.call('SCARD',KEYS[4])-1>=tonumber(ARGV[6]) then return 'capacity' end
if not migrating then
 if raw=='' then if delta.expected_revision~=cjson.null then return 'retry' end
 else
  local previous=cjson.decode(raw)
  if previous.kind~='hot' or previous.schema_version~=3 then return 'history' end
  if delta.expected_revision~=previous.revision then return 'retry' end
 end
end
local deleted={}; local oldmeta={}; local parsed={}; local count=redis.call('HLEN',KEYS[5])
if migrating and (count~=0 or redis.call('EXISTS',KEYS[6],KEYS[7],KEYS[8])~=0) then return 'history' end
local function validkey(key)
 return type(key)=='string' and #key==#KEYS[3]+11+64 and string.sub(key,1,#KEYS[3]+11)==KEYS[3]..':operation:'
end
for _,id in ipairs(delta.delete) do
 deleted[id]=true
 local encoded=redis.call('HGET',KEYS[5],id)
 if encoded then
  local meta=cjson.decode(encoded); oldmeta[id]=meta
  local expiry=redis.call('ZSCORE',KEYS[6],id)
  if not expiry or tonumber(expiry)>now or redis.call('SISMEMBER',KEYS[8],id)==1 then return 'protected' end
  if not validkey(rowkeys[id]) or meta.key~=rowkeys[id] or not sequence(meta.index_fields) then return 'history' end
  local kind=redis.call('TYPE',meta.key).ok; if kind~='none' and kind~='string' then return 'history' end
  count=count-1
 end
end
for id,value in pairs(delta.put) do
 if not validkey(rowkeys[id]) or not metas[id] then return 'malformed' end
 local kind=redis.call('TYPE',rowkeys[id]).ok; if kind~='none' and kind~='string' then return 'history' end
 local row=cjson.decode(value); local meta=cjson.decode(metas[id]); parsed[id]=meta
 if row.schema_version~=3 or row.kind~='operation' or row.id~=id or row.conversation~=ARGV[3] or meta.key~=rowkeys[id] or not sequence(meta.index_fields) then return 'malformed' end
 local terminal=row.status=='completed' or row.status=='failed'
 if (terminal and meta.status~='terminal') or (not terminal and meta.status~='protected') then return 'malformed' end
 local existing=redis.call('HGET',KEYS[5],id)
 if existing and not deleted[id] then
  local previous=cjson.decode(existing)
  if previous.key~=rowkeys[id] then return 'history' end
 else count=count+1 end
 if terminal and not delta.terminal_retention_ms[id] and (deleted[id] or not redis.call('ZSCORE',KEYS[6],id)) then return 'malformed' end
end
if count>tonumber(ARGV[9]) then return 'receipts' end
if hot=='' then
 if count~=0 or redis.call('SCARD',KEYS[8])~=0 then return 'protected' end
 local removals=0; local fields={}; local fieldcount=0
 for id,meta in pairs(oldmeta) do
  if redis.call('ZSCORE',KEYS[6],id) then removals=removals+1 end
  for _,field in ipairs(meta.index_fields) do
   if not fields[field] and redis.call('HGET',KEYS[7],field)==id then fields[field]=true; fieldcount=fieldcount+1 end
  end
 end
 if redis.call('ZCARD',KEYS[6])~=removals or redis.call('HLEN',KEYS[7])~=fieldcount then return 'history' end
end

for id,duration in pairs(delta.terminal_retention_ms) do
 if not delta.put[id] or not parsed[id] or parsed[id].status~='terminal' or duration<=0 or duration==math.huge or duration%1~=0 then return 'malformed' end
end
for id,meta in pairs(parsed) do
 if meta.status=='terminal' then
  local duration=delta.terminal_retention_ms[id]
  local deadline=migration[id] or (duration and now+duration or tonumber(redis.call('ZSCORE',KEYS[6],id)))
  if not deadline or deadline~=deadline or deadline>9007199254740991 or deadline%1~=0 then return 'malformed' end
  if deadline<=now then return 'retry' end
  meta.deadline=deadline
 end
end
for field,owner in pairs(delta.token_index_put) do
 if not delta.put[owner] and (deleted[owner] or redis.call('HEXISTS',KEYS[5],owner)==0) then return 'malformed' end
end
-- Every key, header, index and retention precondition has passed before writes.
for _,id in ipairs(delta.delete) do
 local meta=oldmeta[id]
 if meta then
  for _,field in ipairs(meta.index_fields) do if redis.call('HGET',KEYS[7],field)==id then redis.call('HDEL',KEYS[7],field) end end
  redis.call('DEL',meta.key)
 end
 redis.call('HDEL',KEYS[5],id); redis.call('ZREM',KEYS[6],id); redis.call('SREM',KEYS[8],id)
end
for id,value in pairs(delta.put) do
 local meta=parsed[id]
 if meta.status=='terminal' then
  local deadline=meta.deadline
  redis.call('SET',rowkeys[id],value,'PXAT',deadline); redis.call('ZADD',KEYS[6],deadline,id); redis.call('SREM',KEYS[8],id)
 else
  redis.call('SET',rowkeys[id],value); redis.call('ZREM',KEYS[6],id); redis.call('SADD',KEYS[8],id)
 end
 redis.call('HSET',KEYS[5],id,metas[id])
end
for field,owner in pairs(delta.token_index_put) do redis.call('HSET',KEYS[7],field,owner) end
if hot=='' then
 redis.call('DEL',KEYS[3],KEYS[9]); redis.call('SREM',KEYS[4],ARGV[3])
else redis.call('SET',KEYS[9],redis.call('HLEN',KEYS[7])); redis.call('SET',KEYS[3],hot); redis.call('SADD',KEYS[4],ARGV[3]) end
return 'ok'
"""
