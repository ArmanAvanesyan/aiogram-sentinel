"""Bounded atomic scripts. All conditional checks precede writes."""

_TYPES = r"""
local function types(keys, expected)
 for i,k in ipairs(keys) do
  local t=redis.call('TYPE',k).ok
  if t~='none' and t~=expected[i] then return false end
 end
 return true
end
local function namespace(created, expected, config, established)
 if redis.call('GET',created)~=expected then return false end
 if redis.call('EXISTS',established)==1 and redis.call('EXISTS',config)==0 then return false end
 return true
end
"""

INITIALIZE = (
    _TYPES
    + r"""
if not types(KEYS, {'string','set','string','zset','set','string','hash','string','zset','zset','string'}) then return redis.error_reply('IDLE_INCONSISTENT key type') end
local existing=redis.call('GET',KEYS[1])
if existing then
 local at,profile=string.match(existing,'^([^:]+):(.+)$')
 local stamp=tonumber(at)
 if not stamp or stamp~=stamp or stamp<=0 or stamp==math.huge then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
 if profile~=ARGV[1] then return 'profile-mismatch' end
 if tonumber(ARGV[2])==3 then
  local format=redis.call('GET',KEYS[8]);if not format then return redis.error_reply('IDLE_INCONSISTENT missing format marker') end
  local ok,body=pcall(cjson.decode,format)
  if not ok or body.format~=3 or body.history~=existing then return redis.error_reply('IDLE_INCONSISTENT storage format history') end
 end
 local proof=redis.call('GET',KEYS[11])
 if proof and proof~=at then return redis.error_reply('IDLE_INCONSISTENT namespace history proof') end
 if not proof then redis.call('SET',KEYS[11],at) end
 return existing
end
if redis.call('SCARD',KEYS[2])>0 or redis.call('EXISTS',KEYS[3])>0 or redis.call('ZCARD',KEYS[4])>0 or redis.call('SCARD',KEYS[5])>0 or redis.call('EXISTS',KEYS[6])>0 or redis.call('HLEN',KEYS[7])>0 or redis.call('EXISTS',KEYS[8])>0 or redis.call('ZCARD',KEYS[9])>0 or redis.call('ZCARD',KEYS[10])>0 or redis.call('EXISTS',KEYS[11])>0 then return redis.error_reply('IDLE_INCONSISTENT missing history marker') end
local tm=redis.call('TIME'); local value=tm[1]..'.'..string.format('%06d',tonumber(tm[2]))..':'..ARGV[1]
redis.call('SET',KEYS[1],value)
redis.call('SET',KEYS[11],tm[1]..'.'..string.format('%06d',tonumber(tm[2])))
if tonumber(ARGV[2])==3 then
 redis.call('SET',KEYS[8],cjson.encode({format=3,operation_id='namespace-bootstrap',previous_history=value,history=value}))
end
return value
"""
)

READ = (
    _TYPES
    + r"""
if not types(KEYS, {'string','string','set','string','string','string','hash'}) then return redis.error_reply('IDLE_INCONSISTENT key type') end
if not namespace(KEYS[5],ARGV[2],KEYS[4],KEYS[6]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
local tm=redis.call('TIME')
return {redis.call('GET',KEYS[1]) or '',redis.call('GET',KEYS[2]) or '',redis.call('GET',KEYS[4]) or '',redis.call('SISMEMBER',KEYS[3],ARGV[1]),tm[1],tm[2],redis.call('HEXISTS',KEYS[7],ARGV[1])}
"""
)

# KEYS record,job,due,live,config,routes. ARGV old,new,job,member,route,
# configraw,claimtoken,claimgeneration,maxrecords. Empty strings represent absence.
COMMIT = (
    _TYPES
    + r"""
if not types(KEYS, {'string','string','zset','set','string','set','string','zset','string','string','hash'}) then return redis.error_reply('IDLE_INCONSISTENT key type') end
if not namespace(KEYS[9],ARGV[14],KEYS[5],KEYS[10]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if redis.call('HEXISTS',KEYS[11],ARGV[4])==1 then return redis.error_reply('IDLE_INCONSISTENT parked conversation') end
local tm=redis.call('TIME'); local now=tonumber(tm[1])+tonumber(tm[2])/1000000
local old=redis.call('GET',KEYS[1]) or ''
if old~=ARGV[1] or (redis.call('GET',KEYS[2]) or '')~=ARGV[10] then return 'conflict' end
if ARGV[11]~='' and (redis.call('GET',KEYS[7])~=ARGV[11] or redis.call('PTTL',KEYS[7])<=0) then return 'ownership' end
if (redis.call('GET',KEYS[5]) or '')~=ARGV[6] then return 'config' end
if tonumber(ARGV[13])>0 and tonumber(ARGV[13])<=now then return 'expired' end
if ARGV[7]~='' then
 local raw=redis.call('GET',KEYS[2]); if not raw then return 'ownership' end
 local j=cjson.decode(raw)
 if j.token~=ARGV[7] or j.generation~=tonumber(ARGV[8]) or j.lease_until<=now then return 'ownership' end
end
if old=='' and ARGV[2]~='' and redis.call('SCARD',KEYS[4])>=tonumber(ARGV[9]) then return 'capacity' end
if ARGV[2]=='' then
 redis.call('DEL',KEYS[1],KEYS[2]); redis.call('ZREM',KEYS[3],ARGV[4]); redis.call('SREM',KEYS[4],ARGV[4]); redis.call('ZREM',KEYS[8],ARGV[4]); if redis.call('ZCARD',KEYS[3])==0 then redis.call('SREM',KEYS[6],ARGV[5]) end; return 'ok'
end
local job=nil
if ARGV[3]~='' then job=cjson.decode(ARGV[3]) end
redis.call('SET',KEYS[1],ARGV[2]); redis.call('SADD',KEYS[4],ARGV[4]); redis.call('ZADD',KEYS[8],ARGV[12],ARGV[4]); if job then redis.call('SADD',KEYS[6],ARGV[5]) end
if job then redis.call('SET',KEYS[2],ARGV[3]); redis.call('ZADD',KEYS[3],job.eligible_at,ARGV[4])
else redis.call('DEL',KEYS[2]); redis.call('ZREM',KEYS[3],ARGV[4]); if redis.call('ZCARD',KEYS[3])==0 then redis.call('SREM',KEYS[6],ARGV[5]) end end
return 'ok'
"""
)

# All jobs remain indexed while leased. Candidate keys supplied from bounded route scan.
CLAIM = (
    _TYPES
    + r"""
local jobs=#KEYS-4
local expected={'zset'}; for i=2,#KEYS do expected[i]='string' end
if not types(KEYS,expected) then return redis.error_reply('IDLE_INCONSISTENT key type') end
if not namespace(KEYS[#KEYS-2],ARGV[#ARGV],KEYS[#KEYS-1],KEYS[#KEYS]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
for i=2,jobs+1 do
 local raw=redis.call('GET',KEYS[i]); if raw and raw==ARGV[jobs+i+1] then
  local j=cjson.decode(raw)
  if type(j.generation)~='number' or type(j.eligible_at)~='number' or type(j.deadline)~='number' or type(j.lease_until)~='number' then return redis.error_reply('IDLE_INCONSISTENT job') end
 end
end
local tm=redis.call('TIME'); local now=tonumber(tm[1])+tonumber(tm[2])/1000000
local out={}
for i=2,jobs+1 do
 local raw=redis.call('GET',KEYS[i])
 if raw and raw==ARGV[jobs+i+1] then
  local j=cjson.decode(raw)
  if j.eligible_at<=now and (not j.token or j.token==cjson.null or j.lease_until<=now) then
   j.token=ARGV[2]..':'..i; j.lease_until=now+tonumber(ARGV[1]); j.eligible_at=j.lease_until
   local encoded=cjson.encode(j); redis.call('SET',KEYS[i],encoded)
   redis.call('ZADD',KEYS[1],j.eligible_at,ARGV[i+1]); table.insert(out,ARGV[i+1]); table.insert(out,encoded)
  end
 end
end
return out
"""
)

# KEYS job,due; ARGV token,generation,action,lease/retry,member.
LEASE = (
    _TYPES
    + r"""
if not types(KEYS, {'string','zset','string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT key type') end
local tm=redis.call('TIME'); local now=tonumber(tm[1])+tonumber(tm[2])/1000000
if not namespace(KEYS[3],ARGV[7],KEYS[4],KEYS[5]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
local raw=redis.call('GET',KEYS[1]); if not raw then return '' end
local j=cjson.decode(raw)
if j.token~=ARGV[1] or j.generation~=tonumber(ARGV[2]) or j.lease_until<=now then return '' end
if ARGV[3]=='check' then return raw end
if ARGV[3]=='renew' then
 local requested=tonumber(ARGV[8])
 if not requested or requested~=requested or requested<=0 or requested==math.huge then return redis.error_reply('IDLE_INCONSISTENT renewal timestamp') end
 if j.renew_id==ARGV[6] or (j.renew_at and requested<=j.renew_at) then return raw end
 j.renew_id=ARGV[6]; j.renew_at=requested; j.lease_until=now+tonumber(ARGV[4]); j.eligible_at=j.lease_until
else
 if ARGV[4]=='' then redis.call('DEL',KEYS[1]); redis.call('ZREM',KEYS[2],ARGV[5]); return 'released' end
 j.generation=j.generation+1; j.deadline=tonumber(ARGV[4]); j.eligible_at=j.deadline; j.token=cjson.null; j.lease_until=0; j.renew_id=nil; j.renew_at=nil
end
local encoded=cjson.encode(j); redis.call('SET',KEYS[1],encoded); redis.call('ZADD',KEYS[2],j.eligible_at,ARGV[5]); return encoded
"""
)

CONFIG = (
    _TYPES
    + r"""
if not types(KEYS, {'string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT key type') end
if not namespace(KEYS[2],ARGV[3],KEYS[1],KEYS[3]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[1] then return 'conflict' end
redis.call('SET',KEYS[1],ARGV[2]); redis.call('SET',KEYS[3],'1'); return 'ok'
"""
)

PARK = (
    _TYPES
    + r"""
if not types(KEYS, {'string','string','zset','hash','set','string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT key type') end
if not namespace(KEYS[6],ARGV[8],KEYS[7],KEYS[8]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[1] or (redis.call('GET',KEYS[2]) or '')~=ARGV[2] then return 0 end
if ARGV[5]=='release' then
 redis.call('HDEL',KEYS[4],ARGV[3]); if ARGV[6]~='' then redis.call('ZADD',KEYS[3],ARGV[6],ARGV[3]); redis.call('SADD',KEYS[5],ARGV[7]) end; return 1
end
redis.call('HSET',KEYS[4],ARGV[3],ARGV[4]); redis.call('ZREM',KEYS[3],ARGV[3]); return 1
"""
)

CONFIG_READ = (
    _TYPES
    + r"""
if not types(KEYS, {'string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT key type') end
if not namespace(KEYS[2],ARGV[1],KEYS[1],KEYS[3]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
return redis.call('GET',KEYS[1]) or ''
"""
)
