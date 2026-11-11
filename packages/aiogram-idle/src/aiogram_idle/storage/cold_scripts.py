"""Format-three observation and commit scripts; all checks precede every write."""

from .redis_scripts import COMMIT, READ

# Keep the original history/configuration/park checks in the same server sample.
READ_COLD = (
    READ.replace(
        "'string','string','set','string','string','string','hash'",
        "'string','string','set','string','string','string','hash','string','hash','zset','string'",
    )
    .replace(
        "return {redis.call('GET',KEYS[1])",
        """
local pending=redis.call('GET',KEYS[8]) or ''
if pending~='' and redis.call('PTTL',KEYS[8])~=-1 then return redis.error_reply('IDLE_INCONSISTENT protected operation lifetime') end
local meta=ARGV[3]~='' and redis.call('HGET',KEYS[9],ARGV[3]) or false
if meta and meta~=KEYS[11] then return redis.error_reply('IDLE_INCONSISTENT receipt identity') end
local receipt=redis.call('GET',KEYS[11]) or ''
local expiry=ARGV[3]~='' and redis.call('ZSCORE',KEYS[10],ARGV[3]) or false
local now=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
if expiry and (not tonumber(expiry) or tonumber(expiry)~=tonumber(expiry) or tonumber(expiry)<=0
 or tonumber(expiry)>9007199254740991 or tonumber(expiry)%1~=0) then
 return redis.error_reply('IDLE_INCONSISTENT receipt expiry proof') end
if (meta and not expiry) or (expiry and not meta) then return redis.error_reply('IDLE_INCONSISTENT receipt membership proof') end
if meta and receipt=='' and (not expiry or tonumber(expiry)>now) then return redis.error_reply('IDLE_INCONSISTENT promised receipt missing') end
if receipt~='' and not meta then return redis.error_reply('IDLE_INCONSISTENT receipt index missing') end
local result=''
if receipt~='' then
 local ok,row=pcall(cjson.decode,receipt)
 if not ok or type(row)~='table' then return redis.error_reply('IDLE_INCONSISTENT receipt shape') end
 if row.schema_version~=3 or row.key~=ARGV[1] or row.operation_id~=ARGV[3]
  or type(row.fingerprint)~='string' or row.fingerprint=='' or row.expires_at~=tonumber(expiry) then
  return redis.error_reply('IDLE_INCONSISTENT receipt identity proof') end
 if tonumber(expiry)>now and redis.call('PEXPIRETIME',KEYS[11])~=tonumber(expiry) then
  return redis.error_reply('IDLE_INCONSISTENT receipt physical expiry') end
 if row.result_ref and row.result_ref~=cjson.null then
  local ref=row.result_ref
  if type(ref)~='string' or #ref~=64 or string.find(ref,'[^a-f0-9]') then return redis.error_reply('IDLE_INCONSISTENT result identity') end
  local key=ARGV[4]..ref
  local t=redis.call('TYPE',key).ok
  if t~='none' and t~='string' then return redis.error_reply('IDLE_INCONSISTENT result key type') end
  result=redis.call('GET',key) or ''
  if result=='' and (not expiry or tonumber(expiry)>now) then return redis.error_reply('IDLE_INCONSISTENT promised result missing') end
  if tonumber(expiry)>now and redis.call('PEXPIRETIME',key)<tonumber(expiry) then
   return redis.error_reply('IDLE_INCONSISTENT promised result lifetime') end
 end
end
local expired=redis.call('ZRANGEBYSCORE',KEYS[10],'-inf',now,'LIMIT',0,32)
return {redis.call('GET',KEYS[1])""",
    )
    .replace(
        "redis.call('HEXISTS',KEYS[7],ARGV[1])}",
        "redis.call('HEXISTS',KEYS[7],ARGV[1]),pending,receipt,result,expiry or '',redis.call('HLEN',KEYS[9]),expired}",
    )
)

IDENTITY = r"""
local function identity(value)
 if type(value)~='string' or value=='' or #value>1024 then return false end
 local count=0
 for i=1,#value do local b=string.byte(value,i); if b<128 or b>=192 then count=count+1 end end
 return count<=256
end
local function cold_fields(value,allowed,total)
 if type(value)~='table' then return false end
 local count=0
 for name,_ in pairs(value) do if not allowed[name] then return false end; count=count+1 end
 return count==total
end
"""

_PREFLIGHT = (
    IDENTITY
    + r"""
local ok,cold=pcall(cjson.decode,ARGV[15])
local maxsafe=9007199254740991
local nowms=tonumber(tm[1])*1000+math.floor(tonumber(tm[2])/1000)
if not ok or type(cold)~='table' or type(cold.pending)~='string' or type(cold.operation_id)~='string'
 or (cold.operation_id~='' and not identity(cold.operation_id)) or type(cold.gc)~='table' or #cold.gc>32 or type(cold.row)~='string'
 or type(cold.blob)~='string' or type(cold.retention_ms)~='number' or cold.retention_ms<=0
 or cold.retention_ms~=cold.retention_ms or cold.retention_ms>maxsafe or cold.retention_ms%1~=0
 or nowms+cold.retention_ms>maxsafe or type(cold.receipt_prefix)~='string'
 or type(cold.result_prefix)~='string' or #KEYS~=17+#cold.gc then
 return redis.error_reply('IDLE_INCONSISTENT cold delta or unsafe exact TTL') end
local allowed={pending=true,operation_id=true,gc=true,row=true,blob=true,retention_ms=true,receipt_prefix=true,result_prefix=true}
for name,_ in pairs(cold) do if not allowed[name] then return redis.error_reply('IDLE_INCONSISTENT cold delta fields') end end
for i,_ in pairs(cold.gc) do if type(i)~='number' or i%1~=0 or i<1 or i>#cold.gc then return redis.error_reply('IDLE_INCONSISTENT cold GC array') end end
local expectations={'string','hash','zset','string','string','zset'}
for i=12,17+#cold.gc do
 local actual=redis.call('TYPE',KEYS[i]).ok
 local expected=expectations[i-11] or 'string'
 if actual~='none' and actual~=expected then return redis.error_reply('IDLE_INCONSISTENT cold key type') end
end
if redis.call('HLEN',KEYS[13])~=redis.call('ZCARD',KEYS[14]) then return redis.error_reply('IDLE_INCONSISTENT receipt index count') end
local function rowkey(key)
 local suffix=string.sub(key,#cold.receipt_prefix+1)
 return string.sub(key,1,#cold.receipt_prefix)==cold.receipt_prefix and #suffix==64 and not string.find(suffix,'[^a-f0-9]')
end
if not rowkey(KEYS[15]) then return redis.error_reply('IDLE_INCONSISTENT receipt scope') end
if cold.pending~='' then
 local valid,protected=pcall(cjson.decode,cold.pending)
 if not valid or not cold_fields(protected,{key=true,operation_id=true,value=true},3) or protected.key~=ARGV[4]
  or type(protected.operation_id)~='string' or protected.operation_id=='' or type(protected.value)~='string' then
  return redis.error_reply('IDLE_INCONSISTENT protected operation proof') end
 local good,encoded=pcall(cjson.decode,protected.value)
 if not good or type(encoded)~='table' or encoded.schema_version~=3 or type(encoded.value)~='table'
  or encoded.value.type~='PendingOperation' or type(encoded.value.value)~='table'
  or encoded.value.value.operation_id~=protected.operation_id then
  return redis.error_reply('IDLE_INCONSISTENT protected operation identity') end
end
if ARGV[2]~='' then
 local valid,hot=pcall(cjson.decode,ARGV[2])
 if not valid or not cold_fields(hot,{schema_version=true,kind=true,pending_ref=true,state=true},4) or hot.schema_version~=3 or hot.kind~='idle-hot' or type(hot.state)~='string' then
  return redis.error_reply('IDLE_INCONSISTENT hot state header') end
 if (hot.pending_ref~=cjson.null and type(hot.pending_ref)~='string')
  or (cold.pending=='' and hot.pending_ref~=cjson.null) then
  return redis.error_reply('IDLE_INCONSISTENT protected operation reference') end
 if cold.pending~='' and cjson.decode(cold.pending).operation_id~=hot.pending_ref then
  return redis.error_reply('IDLE_INCONSISTENT protected operation reference') end
elseif cold.pending~='' then return redis.error_reply('IDLE_INCONSISTENT unreferenced operation') end
local removed=0
local seen={}
for i,item in ipairs(cold.gc) do
 if not cold_fields(item,{id=true,key=true},2) or not identity(item.id) or type(item.key)~='string'
  or item.key~=KEYS[17+i] or not rowkey(item.key) or seen[item.id] then
  return redis.error_reply('IDLE_INCONSISTENT cold expiry identity') end
 seen[item.id]=true
 local metadata=redis.call('HGET',KEYS[13],item.id)
 if metadata and metadata~=item.key then return redis.error_reply('IDLE_INCONSISTENT cold expiry metadata') end
 local expiry=redis.call('ZSCORE',KEYS[14],item.id)
 if (metadata and not expiry) or (expiry and not metadata) then return redis.error_reply('IDLE_INCONSISTENT cold expiry membership') end
 if metadata and tonumber(expiry)>nowms then return 'protected' end
 if metadata then removed=removed+1 end
end
local existing=false
local proposed=nil
local oldblobexpiry=-2
local newexpiry=nowms+cold.retention_ms
local expirytext=string.format('%.0f',newexpiry)
if cold.row~='' then
 if cold.operation_id=='' then return redis.error_reply('IDLE_INCONSISTENT missing receipt operation') end
 local oldkey=redis.call('HGET',KEYS[13],cold.operation_id)
 if oldkey and oldkey~=KEYS[15] then return redis.error_reply('IDLE_INCONSISTENT receipt key identity') end
 local oldexpiry=redis.call('ZSCORE',KEYS[14],cold.operation_id)
 if (oldkey and not oldexpiry) or (oldexpiry and not oldkey) then return redis.error_reply('IDLE_INCONSISTENT receipt expiry membership') end
 local raw=redis.call('GET',KEYS[15])
 if raw and not oldkey then return redis.error_reply('IDLE_INCONSISTENT receipt membership missing') end
 if oldkey and tonumber(oldexpiry)>nowms and not raw then return redis.error_reply('IDLE_INCONSISTENT promised receipt missing') end
 local valid; valid,proposed=pcall(cjson.decode,cold.row)
 if not valid or not cold_fields(proposed,{schema_version=true,key=true,operation_id=true,fingerprint=true,expires_at=true,result=true,result_ref=true},7) or proposed.schema_version~=3 or proposed.operation_id~=cold.operation_id
  or proposed.key~=ARGV[4] or not identity(proposed.fingerprint) or proposed.expires_at~=0 then return redis.error_reply('IDLE_INCONSISTENT receipt proof') end
 local isref=proposed.result_ref~=cjson.null
 if isref then
  local ref=proposed.result_ref
  if type(ref)~='string' or #ref~=64 or string.find(ref,'[^a-f0-9]') or proposed.result~=cjson.null
   or cold.blob=='' or KEYS[16]~=cold.result_prefix..ref then return redis.error_reply('IDLE_INCONSISTENT result proof') end
 elseif type(proposed.result)~='string' or cold.blob~='' then return redis.error_reply('IDLE_INCONSISTENT inline result proof') end
 if raw and tonumber(oldexpiry)>nowms then
  local good,prior=pcall(cjson.decode,raw)
  if not good or not cold_fields(prior,{schema_version=true,key=true,operation_id=true,fingerprint=true,expires_at=true,result=true,result_ref=true},7) or prior.schema_version~=3 or prior.operation_id~=cold.operation_id
   or prior.key~=ARGV[4] or prior.expires_at~=tonumber(oldexpiry) then return redis.error_reply('IDLE_INCONSISTENT existing receipt proof') end
  if prior.fingerprint~=proposed.fingerprint then return 'fingerprint' end
  if prior.result~=proposed.result or prior.result_ref~=proposed.result_ref then return redis.error_reply('IDLE_INCONSISTENT original result changed') end
  if redis.call('PEXPIRETIME',KEYS[15])~=tonumber(oldexpiry) then return redis.error_reply('IDLE_INCONSISTENT receipt physical expiry') end
  existing=true
 elseif oldkey and not seen[cold.operation_id] then removed=removed+1 end
 if not existing and redis.call('HLEN',KEYS[13])-removed>=tonumber(ARGV[16]) then return 'receipt_capacity' end
 if cold.blob~='' then
  local oldblob=redis.call('GET',KEYS[16])
  if oldblob and oldblob~=cold.blob then return redis.error_reply('IDLE_INCONSISTENT immutable result conflict') end
  oldblobexpiry=redis.call('PEXPIRETIME',KEYS[16])
  if oldblobexpiry==-1 or (existing and (not oldblob or oldblobexpiry<tonumber(oldexpiry))) then
   return redis.error_reply('IDLE_INCONSISTENT promised result lifetime') end
 end
elseif cold.blob~='' then return redis.error_reply('IDLE_INCONSISTENT unreferenced result') end
"""
)

_APPLY = r"""
for _,item in ipairs(cold.gc) do
 redis.call('DEL',item.key); redis.call('HDEL',KEYS[13],item.id); redis.call('ZREM',KEYS[14],item.id)
end
if cold.pending=='' then redis.call('DEL',KEYS[12])
else redis.call('SET',KEYS[12],cold.pending); redis.call('PERSIST',KEYS[12]) end
if proposed and not existing then
 proposed.expires_at=0
 local header=cjson.encode(proposed)
 header=string.gsub(header,'"expires_at":0','"expires_at":'..expirytext,1)
 redis.call('SET',KEYS[15],header,'PXAT',expirytext)
 redis.call('HSET',KEYS[13],cold.operation_id,KEYS[15]); redis.call('ZADD',KEYS[14],expirytext,cold.operation_id)
 if cold.blob~='' then
  if oldblobexpiry==-2 then redis.call('SET',KEYS[16],cold.blob,'PXAT',expirytext)
  elseif oldblobexpiry<newexpiry then redis.call('PEXPIREAT',KEYS[16],expirytext) end
 end
end
if redis.call('HLEN',KEYS[13])==0 then
 redis.call('DEL',KEYS[13],KEYS[14]); redis.call('ZREM',KEYS[17],ARGV[4])
else
 local first=redis.call('ZRANGE',KEYS[14],0,0,'WITHSCORES')
 if #first>0 then redis.call('ZADD',KEYS[17],first[2],ARGV[4]) end
end
"""


def compose_commit(extra_preflight: str = "", extra_apply: str = "") -> str:
    """Compile trusted module literals, with every extension check before writes.

    Canonical component storage owns and preflights the suffix following the fixed
    cold prefix and its bounded GC keys. This is not an application Lua API.
    """
    preflight = _PREFLIGHT
    if extra_preflight:
        preflight = preflight.replace("#KEYS~=17+#cold.gc", "#KEYS<17+#cold.gc")
    elif extra_apply:
        raise ValueError("An extended commit requires its complete preflight")
    script = COMMIT.replace("types(KEYS,", "types({unpack(KEYS,1,11)},", 1)
    script = script.replace(
        "if old=='' and ARGV[2]", preflight + "\n" + extra_preflight + "\nif old=='' and ARGV[2]", 1
    )
    apply = _APPLY + "\n" + extra_apply
    position = script.rfind("return 'ok'")
    script = script[:position] + apply + "\n" + script[position:]
    return script.replace(
        " redis.call('DEL',KEYS[1],KEYS[2]);", apply + "\n redis.call('DEL',KEYS[1],KEYS[2]);", 1
    )


COMMIT_COLD = compose_commit()
