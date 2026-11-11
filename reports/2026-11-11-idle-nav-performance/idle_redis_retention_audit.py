import asyncio,time,json
from dataclasses import replace
from uuid import uuid4
from redis.asyncio import Redis
from aiogram_idle import IdleConfig, IdleConversationKey
from aiogram_idle.storage.redis import RedisIdleBackend
from aiogram_idle.errors import Overloaded

async def run(retention, paced=False):
 client=Redis.from_url('redis://127.0.0.1:16520/0')
 prefix='receipt-audit:'+uuid4().hex
 backend=RedisIdleBackend(redis=client,prefix=prefix,config=IdleConfig(recovery_retention_seconds=retention))
 key=IdleConversationKey('perf',1,2,2)
 await backend.open_session(key,lifetime_seconds=3600,operation_id='open')
 start=time.perf_counter(); fail=None;samples=[]
 try:
  for i in range(1,141):
   if paced and i==100: await asyncio.sleep(2.1)
   for phase in ('prepare','commit'):
    current=await backend.load(key)
    try:
     await backend.transition(key,expected_version=current.version,operation_id=f'{i}:{phase}',fingerprint=f'{i}:{phase}',transform=lambda old:replace(old,components={'opaque':'x'}))
    except Overloaded as e:
     fail={'activation':i,'phase':phase,'error':str(e)};break
   if i in (32,64,96,100,128,140) or fail:
    engine,raw,_=await backend._store.read(key)
    samples.append({'activation':i,'retained':len(engine._receipts.items[key]),'bytes':len(raw),'elapsed':round(time.perf_counter()-start,3),'min_expiry_in':round(min(x.expires_at for x in engine._receipts.items[key].values())-backend.clock.now(),3)})
   if fail:break
  return {'configured_retention':backend.config.recovery_retention_seconds,'paced':paced,'fail':fail,'samples':samples}
 finally:
  async for k in client.scan_iter(match=prefix+':*'):await client.delete(k)
  await backend.close();await client.aclose()
async def main():
 for retention,paced in ((2,False),(2,True),(3600,False)):
  print(json.dumps(await run(retention,paced)),flush=True)
asyncio.run(main())
