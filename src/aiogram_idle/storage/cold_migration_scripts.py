"""Fenced, bounded migration pages; old source remains authoritative until cutover."""

# Shared internal Lua preflight is intentionally reused.
# pyright: reportPrivateUsage=false
from .cold_scripts import IDENTITY
from .redis_scripts import _TYPES

COPY = (
    IDENTITY
    + _TYPES
    + r"""
local expected={'string','string','string','string','string','hash','hash','string','hash','zset','zset','string','string','string'}
for i=15,#KEYS do expected[i]='string' end
if not types(KEYS,expected) then return redis.error_reply('IDLE_INCONSISTENT migration key type') end
if not namespace(KEYS[4],ARGV[4],KEYS[3],KEYS[5]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if redis.call('GET',KEYS[14])~=ARGV[18] or redis.call('PTTL',KEYS[14])<=0 then return 'ownership' end
if redis.call('HEXISTS',KEYS[6],ARGV[5])==1 then return 'parked' end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[1] or (redis.call('GET',KEYS[2]) or '')~=ARGV[2]
 or (redis.call('GET',KEYS[3]) or '')~=ARGV[3] then return 'conflict' end
local tm=redis.call('TIME'); local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
if ARGV[2]~='' then
 local valid,job=pcall(cjson.decode,ARGV[2])
 if not valid or type(job)~='table' then return redis.error_reply('IDLE_INCONSISTENT migration job') end
 if job.token and job.token~=cjson.null and job.lease_until>now/1000 then return 'active' end
end
local position,nextposition,total=tonumber(ARGV[7]),tonumber(ARGV[8]),tonumber(ARGV[9])
if not position or not nextposition or not total or position%1~=0 or nextposition%1~=0 or total%1~=0
 or position<0 or nextposition<position or nextposition>total then return redis.error_reply('IDLE_INCONSISTENT migration progress') end
local oldsource=redis.call('HGET',KEYS[7],'source')
if oldsource then
 if redis.call('HLEN',KEYS[7])~=4 or redis.call('HGET',KEYS[7],'key')~=ARGV[5] then return redis.error_reply('IDLE_INCONSISTENT migration progress proof') end
 if oldsource~=ARGV[6] or redis.call('HGET',KEYS[7],'position')~=ARGV[7] or redis.call('HGET',KEYS[7],'total')~=ARGV[9] then return 'conflict' end
elseif position~=0 or redis.call('HLEN',KEYS[7])~=0 then return 'conflict' end
local valid,rows=pcall(cjson.decode,ARGV[10])
if not valid or type(rows)~='table' or #rows>1000 or #KEYS~=14+2*#rows then return redis.error_reply('IDLE_INCONSISTENT migration page') end
if redis.call('HLEN',KEYS[9])~=redis.call('ZCARD',KEYS[10]) then return redis.error_reply('IDLE_INCONSISTENT migration index count') end
if #ARGV[1]>33554432 then return redis.error_reply('IDLE_INCONSISTENT migration backup bound') end
local good,proof=pcall(cjson.decode,ARGV[16])
local expiry=tonumber(ARGV[17])
if not good or type(proof)~='table' or proof.schema_version~=3 or proof.kind~='idle-migration-source'
 or proof.history~=ARGV[4] or proof.key~=ARGV[5] or proof.source_sha256~=ARGV[6] or proof.bytes~=#ARGV[1]
 or type(proof.protected)~='boolean' or type(proof.original_replay_until)~='number'
 or proof.original_replay_until<=0 or proof.original_replay_until>9007199254740991 or proof.original_replay_until%1~=0
 or (not proof.protected and proof.original_replay_until~=expiry) or not expiry or expiry%1~=0 or expiry<0 or expiry>9007199254740991
 or (proof.protected and (expiry~=0 or proof.expires_at~=cjson.null))
 or (not proof.protected and (expiry<=0 or proof.expires_at~=expiry)) then return redis.error_reply('IDLE_INCONSISTENT migration source proof') end
local backup=redis.call('GET',KEYS[12]); local metadata=redis.call('GET',KEYS[13])
if (backup and not metadata) or (metadata and not backup) then return redis.error_reply('IDLE_INCONSISTENT migration backup missing') end
if backup and (backup~=ARGV[1] or metadata~=ARGV[16]) then return redis.error_reply('IDLE_INCONSISTENT migration backup changed') end
if backup then
 local physical=redis.call('PEXPIRETIME',KEYS[12]); local metaexpiry=redis.call('PEXPIRETIME',KEYS[13])
 if (expiry==0 and (physical~=-1 or metaexpiry~=-1)) or (expiry>0 and (physical~=expiry or metaexpiry~=expiry)) then
  return redis.error_reply('IDLE_INCONSISTENT migration backup lifetime') end
end
local oldpending=redis.call('GET',KEYS[8])
if oldpending and (oldpending~=ARGV[12] or redis.call('PTTL',KEYS[8])~=-1) then return redis.error_reply('IDLE_INCONSISTENT existing protected migration evidence') end
local staged={}
local seen={}
for i,item in ipairs(rows) do
 local rowkey,blobkey=KEYS[13+2*i],KEYS[14+2*i]
 if not cold_fields(item,{id=true,row_key=true,blob_key=true,row=true,blob=true,expiry=true},6) or not identity(item.id) or seen[item.id]
  or item.row_key~=rowkey or item.blob_key~=blobkey or type(item.row)~='string' or type(item.blob)~='string'
  or type(item.expiry)~='number' or item.expiry<=0 or item.expiry%1~=0 or item.expiry>9007199254740991 then
  return redis.error_reply('IDLE_INCONSISTENT migration receipt delta') end
 seen[item.id]=true
 local suffix=string.sub(rowkey,#ARGV[14]+1)
 if string.sub(rowkey,1,#ARGV[14])~=ARGV[14] or #suffix~=64 or string.find(suffix,'[^a-f0-9]') then
  return redis.error_reply('IDLE_INCONSISTENT migration receipt scope') end
 local ok,row=pcall(cjson.decode,item.row)
 if not ok or not cold_fields(row,{schema_version=true,key=true,operation_id=true,fingerprint=true,expires_at=true,result=true,result_ref=true},7) or row.schema_version~=3 or row.key~=ARGV[5] or row.operation_id~=item.id
  or not identity(row.fingerprint) or row.expires_at~=item.expiry then
  return redis.error_reply('IDLE_INCONSISTENT migration receipt proof') end
 if row.result_ref~=cjson.null then
  local ref=row.result_ref
  if type(ref)~='string' or #ref~=64 or string.find(ref,'[^a-f0-9]') or row.result~=cjson.null
   or item.blob=='' or blobkey~=ARGV[15]..ref then return redis.error_reply('IDLE_INCONSISTENT migration result proof') end
 elseif type(row.result)~='string' or item.blob~='' then return redis.error_reply('IDLE_INCONSISTENT migration inline result') end
 local oldkey=redis.call('HGET',KEYS[9],item.id); local oldexpiry=redis.call('ZSCORE',KEYS[10],item.id)
 local oldrow=redis.call('GET',rowkey)
 if oldkey and oldkey~=rowkey then return redis.error_reply('IDLE_INCONSISTENT migration receipt membership') end
 if (oldkey and not oldexpiry) or (oldexpiry and not oldkey) or (oldrow and not oldkey) then
  return redis.error_reply('IDLE_INCONSISTENT migration receipt membership') end
 if oldkey and tonumber(oldexpiry)~=item.expiry then return redis.error_reply('IDLE_INCONSISTENT migration original expiry changed') end
 if oldkey and tonumber(oldexpiry)>now then
  if not oldrow or oldrow~=item.row or tonumber(oldexpiry)~=item.expiry or redis.call('PEXPIRETIME',rowkey)~=item.expiry then
   return redis.error_reply('IDLE_INCONSISTENT migration existing receipt') end
 end
 local oldblob=item.blob~='' and redis.call('GET',blobkey) or false
 local blobexpiry=item.blob~='' and redis.call('PEXPIRETIME',blobkey) or -2
 if oldblob and oldblob~=item.blob then return redis.error_reply('IDLE_INCONSISTENT migration immutable result') end
 if item.blob~='' and (blobexpiry==-1 or (oldkey and tonumber(oldexpiry)>now and (not oldblob or blobexpiry<item.expiry))) then
  return redis.error_reply('IDLE_INCONSISTENT migration promised result') end
 staged[i]={item=item,rowkey=rowkey,blobkey=blobkey,existing=oldkey and tonumber(oldexpiry)>now,blobexpiry=blobexpiry}
end
if ARGV[13]=='1' then
 if nextposition~=total then return redis.error_reply('IDLE_INCONSISTENT incomplete migration cutover') end
 local ok,hot=pcall(cjson.decode,ARGV[11])
 if not ok or type(hot)~='table' or hot.schema_version~=3 or hot.kind~='idle-hot' then return redis.error_reply('IDLE_INCONSISTENT migration hot cutover') end
 if ARGV[12]~='' then
  local valid,protected=pcall(cjson.decode,ARGV[12])
  if not valid or type(protected)~='table' or protected.key~=ARGV[5] or protected.operation_id~=hot.pending_ref then
   return redis.error_reply('IDLE_INCONSISTENT migration pending cutover') end
 elseif hot.pending_ref~=cjson.null then return redis.error_reply('IDLE_INCONSISTENT missing migration pending') end
end
-- No writes occur before every shape, source, ownership, key type and lifetime check.
if not backup then
 if expiry==0 then redis.call('SET',KEYS[12],ARGV[1]); redis.call('SET',KEYS[13],ARGV[16])
 else local at=string.format('%.0f',expiry); redis.call('SET',KEYS[12],ARGV[1],'PXAT',at); redis.call('SET',KEYS[13],ARGV[16],'PXAT',at) end
end
for _,value in ipairs(staged) do
 local item=value.item
 if item.expiry>now and not value.existing then
  local at=string.format('%.0f',item.expiry)
  redis.call('SET',value.rowkey,item.row,'PXAT',at)
  redis.call('HSET',KEYS[9],item.id,value.rowkey); redis.call('ZADD',KEYS[10],at,item.id)
  if item.blob~='' then
   if value.blobexpiry==-2 then redis.call('SET',value.blobkey,item.blob,'PXAT',at)
   elseif value.blobexpiry<item.expiry then redis.call('PEXPIREAT',value.blobkey,at) end
  end
 end
end
local first=redis.call('ZRANGE',KEYS[10],0,0,'WITHSCORES')
if #first>0 then redis.call('ZADD',KEYS[11],first[2],ARGV[5]) end
if ARGV[13]=='1' then
 redis.call('SET',KEYS[1],ARGV[11])
 if ARGV[12]=='' then redis.call('DEL',KEYS[8]) else redis.call('SET',KEYS[8],ARGV[12]); redis.call('PERSIST',KEYS[8]) end
 redis.call('DEL',KEYS[7])
else redis.call('HSET',KEYS[7],'source',ARGV[6],'position',ARGV[8],'total',ARGV[9],'key',ARGV[5]) end
return 'ok'
"""
)
