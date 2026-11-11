import asyncio, json, time
from dataclasses import replace
from aiogram_idle.config import IdleConfig
from aiogram_idle.models import IdleConversationKey
from aiogram_idle.storage.redis_engine import Engine
from aiogram_idle.errors import Overloaded

KEY=IdleConversationKey('audit-perf',1,2,2)
async def bench(n, step=0, payload_unit=128):
 cfg=IdleConfig(recovery_retention_seconds=2)
 now=1000.0
 eng=Engine(key=KEY,raw='',job='',manifest=None,now=now,config=cfg,created_at=now,storage_format=2)
 await eng.open_session(KEY,lifetime_seconds=10000,operation_id='open')
 raw=eng.envelope(); points=[]; elapsed=time.perf_counter(); total_bytes=0
 for activation in range(1,n+1):
  for stage in ('prepare','commit'):
   now+=step
   eng=Engine(key=KEY,raw=raw,job='',manifest=None,now=now,config=cfg,created_at=1000,storage_format=2)
   current=await eng.load(KEY)
   try:
    await eng.transition(KEY,expected_version=current.version,operation_id=f'{activation}:{stage}',fingerprint=f'{activation}:{stage}',transform=lambda old: replace(old,components={'opaque':'x'*(activation*payload_unit)}))
   except Overloaded as e:
    return {'overloaded_activation':activation,'stage':stage,'now':now,'retained':len(eng._receipts.items[KEY]),'envelope_bytes':len(raw),'elapsed':round(time.perf_counter()-elapsed,4),'message':str(e)}
   raw=eng.envelope();total_bytes+=len(raw)
  if activation in (8,16,32,64,128):
   points.append({'activations':activation,'bytes':len(raw),'receipts':len(eng._receipts.items[KEY]),'elapsed':round(time.perf_counter()-elapsed,4)})
 return {'points':points,'elapsed':round(time.perf_counter()-elapsed,4),'bytes':len(raw),'cumulative_bytes':total_bytes,'retained':len(eng._receipts.items[KEY])}
async def main():
 print('growth='+json.dumps(await bench(64)))
 print('fast_cap='+json.dumps(await bench(140,payload_unit=1)))
 print('advancing_time='+json.dumps(await bench(140,step=.2,payload_unit=1)))
asyncio.run(main())
