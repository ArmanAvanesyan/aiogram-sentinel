"""Fenced pages for an opaque legacy component; source survives until cutover."""

# pyright: reportPrivateUsage=false
from .cold_scripts import IDENTITY
from .redis_scripts import _TYPES

COPY = (
    IDENTITY
    + _TYPES
    + r"""
local expected={'string','string','string','string','string','hash','string','hash','hash','zset','hash','set','string','zset','string','string'}
for i=17,#KEYS do expected[i]='string' end
if not types(KEYS,expected) then return redis.error_reply('IDLE_INCONSISTENT canonical migration key type') end
if not namespace(KEYS[4],ARGV[4],KEYS[3],KEYS[5]) then return redis.error_reply('IDLE_INCONSISTENT canonical migration history') end
if redis.call('GET',KEYS[7])~=ARGV[6] or redis.call('PTTL',KEYS[7])<=0 then return 'ownership' end
if redis.call('HEXISTS',KEYS[6],ARGV[5])==1 then return 'parked' end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[1] or (redis.call('GET',KEYS[2]) or '')~=ARGV[2] or (redis.call('GET',KEYS[3]) or '')~=ARGV[3] then return 'conflict' end
if redis.call('GET',KEYS[15])~=ARGV[16] or redis.call('GET',KEYS[16])~=ARGV[17]
 or redis.call('PTTL',KEYS[15])~=-1 or redis.call('PTTL',KEYS[16])~=-1 then return redis.error_reply('IDLE_INCONSISTENT canonical migration immutable source missing') end
local tm=redis.call('TIME');local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
if ARGV[2]~='' then
 local good,job=pcall(cjson.decode,ARGV[2])
 if not good or type(job)~='table' then return redis.error_reply('IDLE_INCONSISTENT canonical migration job') end
 if job.token and job.token~=cjson.null and job.lease_until>now/1000 then return 'active' end
end
local position,nextposition,total=tonumber(ARGV[8]),tonumber(ARGV[9]),tonumber(ARGV[10])
if not position or not nextposition or not total or position%1~=0 or nextposition%1~=0 or total%1~=0
 or position<0 or nextposition<position or nextposition>total then return redis.error_reply('IDLE_INCONSISTENT canonical migration positions') end
local verified,nextverified,pages=tonumber(ARGV[21]),tonumber(ARGV[22]),tonumber(ARGV[23])
local verifying=ARGV[20]=='verify'
if (ARGV[20]~='copy' and not verifying) or not verified or not nextverified or not pages or verified%1~=0 or nextverified%1~=0 or pages%1~=0 or verified<0 or nextverified<verified or nextverified>total or pages<0
 or (verifying and (position~=total or nextposition~=position)) or (not verifying and (verified~=0 or nextverified~=0)) then return redis.error_reply('IDLE_INCONSISTENT canonical migration verification cursor') end
local progress=redis.call('HGET',KEYS[8],'source')
if progress then
 if redis.call('HLEN',KEYS[8])~=8+pages or progress~=ARGV[7] or redis.call('HGET',KEYS[8],'target')~=ARGV[18]
  or redis.call('HGET',KEYS[8],'key')~=ARGV[5] or redis.call('HGET',KEYS[8],'position')~=ARGV[8]
  or redis.call('HGET',KEYS[8],'total')~=ARGV[10] or redis.call('HGET',KEYS[8],'verified')~=ARGV[21] or redis.call('HGET',KEYS[8],'pages')~=ARGV[23] or redis.call('HGET',KEYS[8],'chain')~=ARGV[24] then return 'conflict' end
elseif position~=0 or redis.call('HLEN',KEYS[8])~=0 or redis.call('HLEN',KEYS[9])~=0
 or redis.call('ZCARD',KEYS[10])~=0 or redis.call('HLEN',KEYS[11])~=0 or redis.call('SCARD',KEYS[12])~=0
 or redis.call('EXISTS',KEYS[13])~=0 then return redis.error_reply('IDLE_INCONSISTENT canonical migration unowned staging') end
local valid,rows=pcall(cjson.decode,ARGV[11])
if not valid or type(rows)~='table' or #rows>1000 or #rows~=(verifying and nextverified-verified or nextposition-position) or #KEYS~=16+#rows then return redis.error_reply('IDLE_INCONSISTENT canonical migration page') end
if redis.call('HLEN',KEYS[9])~=position or redis.call('HLEN',KEYS[9])~=redis.call('ZCARD',KEYS[10])+redis.call('SCARD',KEYS[12]) then return redis.error_reply('IDLE_INCONSISTENT canonical migration count proof') end
if progress and redis.call('GET',KEYS[13])~=tostring(redis.call('HLEN',KEYS[11])) then return redis.error_reply('IDLE_INCONSISTENT canonical migration index witness') end
local plans={};local seen={}
for i,item in ipairs(rows) do
 if not cold_fields(item,{id=true,key=true,row=true,expiry=true,metadata=true,indexes=true},6)
  or not identity(item.id) or seen[item.id] or type(item.row)~='string' or item.key~=KEYS[16+i]
  or type(item.indexes)~='table' or type(item.metadata)~='string' then return redis.error_reply('IDLE_INCONSISTENT canonical migration row') end
 seen[item.id]=true
 local suffix=string.sub(item.key,#ARGV[14]+12)
 if string.sub(item.key,1,#ARGV[14]+11)~=ARGV[14]..':operation:' or #suffix~=64 or string.find(suffix,'[^a-f0-9]') then return redis.error_reply('IDLE_INCONSISTENT canonical migration row scope') end
 local good,row=pcall(cjson.decode,item.row)
 if not good or type(row)~='table' or row.schema_version~=3 or row.kind~='operation' or row.id~=item.id or row.conversation~=ARGV[19]
  or (row.status~='completed' and row.status~='failed' and row.status~='prepared' and row.status~='unknown') then return redis.error_reply('IDLE_INCONSISTENT canonical migration row identity') end
 local terminal=row.status=='completed' or row.status=='failed'
 if type(item.expiry)~='number' or item.expiry%1~=0 or item.expiry<0 or item.expiry>9007199254740991
  or (terminal and item.expiry==0) or (not terminal and item.expiry~=0) then return redis.error_reply('IDLE_INCONSISTENT canonical migration expiry') end
 local okmeta,meta=pcall(cjson.decode,item.metadata)
 if not okmeta or not cold_fields(meta,{key=true,status=true,index_fields=true},3) or meta.key~=item.key
  or meta.status~=(terminal and 'terminal' or 'protected') or type(meta.index_fields)~='table' then return redis.error_reply('IDLE_INCONSISTENT canonical migration metadata') end
 local count=0
 for field,owner in pairs(item.indexes) do
  if type(field)~='string' or not identity(string.sub(field,3)) or #field>1032 or owner~=item.id then return redis.error_reply('IDLE_INCONSISTENT canonical migration reverse index') end
  local previous=redis.call('HGET',KEYS[11],field)
  if previous and previous~=owner then return redis.error_reply('IDLE_INCONSISTENT canonical migration index collision') end
  count=count+1
 end
 if #meta.index_fields~=count then return redis.error_reply('IDLE_INCONSISTENT canonical migration reverse count') end
 for _,field in ipairs(meta.index_fields) do if item.indexes[field]~=item.id then return redis.error_reply('IDLE_INCONSISTENT canonical migration reverse proof') end end
 if verifying then
  if redis.call('HGET',KEYS[9],item.id)~=item.metadata then return redis.error_reply('IDLE_INCONSISTENT canonical migration staged metadata changed') end
  local score=redis.call('ZSCORE',KEYS[10],item.id);local owned=redis.call('SISMEMBER',KEYS[12],item.id)
  if terminal then
   if not score or tonumber(score)~=item.expiry or owned~=0 then return redis.error_reply('IDLE_INCONSISTENT canonical migration staged expiry changed') end
  elseif score or owned~=1 then return redis.error_reply('IDLE_INCONSISTENT canonical migration staged protection changed') end
  local previous=redis.call('GET',item.key);local expiry=redis.call('PEXPIRETIME',item.key)
  if not terminal or item.expiry>now then
   if previous~=item.row or expiry~=(terminal and item.expiry or -1) then return redis.error_reply('IDLE_INCONSISTENT canonical migration promised row missing or changed') end
  elseif previous and previous~=item.row then return redis.error_reply('IDLE_INCONSISTENT canonical migration expired row changed') end
  for field,owner in pairs(item.indexes) do if redis.call('HGET',KEYS[11],field)~=owner then return redis.error_reply('IDLE_INCONSISTENT canonical migration staged reverse owner changed') end end
 else
  if redis.call('HEXISTS',KEYS[9],item.id)==1 or redis.call('EXISTS',item.key)==1 or redis.call('ZSCORE',KEYS[10],item.id) or redis.call('SISMEMBER',KEYS[12],item.id)==1 then return redis.error_reply('IDLE_INCONSISTENT canonical migration duplicate staged identity') end
 end
 table.insert(plans,{item=item,terminal=terminal})
end
if ARGV[13]~='0' and ARGV[13]~='1' then return redis.error_reply('IDLE_INCONSISTENT canonical migration cutover') end
if (ARGV[13]=='1')~=(verifying and nextverified==total) or (ARGV[13]=='1' and ARGV[12]=='') then return redis.error_reply('IDLE_INCONSISTENT canonical migration incomplete cutover') end
if verifying and (#ARGV[25]~=64 or string.find(ARGV[25],'[^a-f0-9]') or redis.call('HEXISTS',KEYS[8],'proof:'..ARGV[22])==1) then return redis.error_reply('IDLE_INCONSISTENT canonical migration page proof') end
-- All shape/type/fence/source/history/count/TTL/index checks precede every write.
if not verifying then
for _,plan in ipairs(plans) do
 local item=plan.item
 if not plan.terminal then redis.call('SET',item.key,item.row)
 elseif item.expiry>now then redis.call('SET',item.key,item.row,'PXAT',string.format('%.0f',item.expiry)) end
 redis.call('HSET',KEYS[9],item.id,item.metadata)
 if plan.terminal then redis.call('ZADD',KEYS[10],string.format('%.0f',item.expiry),item.id)
 else redis.call('SADD',KEYS[12],item.id) end
 for field,owner in pairs(item.indexes) do redis.call('HSET',KEYS[11],field,owner) end
end
end
redis.call('SET',KEYS[13],tostring(redis.call('HLEN',KEYS[11])))
if ARGV[13]=='1' then
 redis.call('SET',KEYS[1],ARGV[12]);redis.call('DEL',KEYS[8])
 local first=redis.call('ZRANGE',KEYS[10],0,0,'WITHSCORES')
 if #first>0 then redis.call('ZADD',KEYS[14],first[2],ARGV[15]) end
else
 local chain=ARGV[24]
 if verifying then chain=redis.sha1hex(chain..ARGV[25]);redis.call('HSET',KEYS[8],'proof:'..ARGV[22],ARGV[25]);pages=pages+1 end
 redis.call('HSET',KEYS[8],'source',ARGV[7],'target',ARGV[18],'position',ARGV[9],'total',ARGV[10],'key',ARGV[5],'verified',ARGV[22],'pages',tostring(pages),'chain',chain)
end
return 'ok'
"""
)
