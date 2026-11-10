"""Atomic namespace checks and whole-conversation compare-and-swap."""

INITIALIZE = """
local profile = redis.call('GET', KEYS[1])
local witness = redis.call('GET', KEYS[2])
if profile then
  if profile ~= ARGV[1] then return 'profile' end
  if not witness or redis.call('SISMEMBER', KEYS[3], '!established') ~= 1 then return 'history' end
  return witness
end
if witness or redis.call('EXISTS', KEYS[3]) == 1 then return 'history' end
local t = redis.call('TIME')
local marker = t[1] .. ':' .. t[2] .. ':' .. ARGV[2]
redis.call('SADD', KEYS[3], '!established')
redis.call('SET', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], marker)
return marker
"""

READ = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2] then
 return {'history'}
end
if redis.call('SISMEMBER', KEYS[4], '!established') ~= 1 then return {'history'} end
local raw = redis.call('GET', KEYS[3])
local indexed = redis.call('SISMEMBER', KEYS[4], ARGV[3])
if (raw and indexed == 0) or (not raw and indexed == 1) then return {'history'} end
local t = redis.call('TIME')
return {'ok', raw or '', t[1], t[2]}
"""

COMMIT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2] then
 return 'history'
end
local live_type = redis.call('TYPE', KEYS[4]).ok
if live_type ~= 'none' and live_type ~= 'set' then return 'history' end
local raw = redis.call('GET', KEYS[3]) or ''
local indexed = redis.call('SISMEMBER', KEYS[4], ARGV[3])
if (raw ~= '' and indexed == 0) or (raw == '' and indexed == 1) then return 'history' end
if redis.call('SISMEMBER', KEYS[4], '!established') ~= 1 then return 'history' end
if raw ~= ARGV[4] then return 'retry' end
if ARGV[7] ~= '' then
 if redis.call('GET', KEYS[5]) ~= ARGV[7] or redis.call('PTTL', KEYS[5]) <= 0 then return 'ownership' end
end
if tonumber(ARGV[8]) > 0 then
 local t = redis.call('TIME')
 if tonumber(t[1])*1000 + math.floor(tonumber(t[2])/1000) >= tonumber(ARGV[8]) then return 'expired' end
end
if ARGV[5] == '' then
 redis.call('DEL', KEYS[3]); redis.call('SREM', KEYS[4], ARGV[3]); return 'ok'
end
if raw == '' and redis.call('SCARD', KEYS[4]) - 1 >= tonumber(ARGV[6]) then return 'capacity' end
redis.call('SET', KEYS[3], ARGV[5]); redis.call('SADD', KEYS[4], ARGV[3]); return 'ok'
"""


SCAN_PAGE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2] then
 return {'history'}
end
if redis.call('SISMEMBER', KEYS[3], '!established') ~= 1 then return {'history'} end
local page = redis.call('SSCAN', KEYS[3], ARGV[3], 'COUNT', ARGV[4])
return {'ok', page[1], page[2]}
"""
