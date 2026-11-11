import asyncio,json,time,sys,collections,argparse
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument("--idle-checkout",type=Path,default=Path(__file__).resolve().parents[3]/"aiogram-idle")
parser.add_argument("--redis-url",default="redis://127.0.0.1:16520/0")
args=parser.parse_args()
sys.path.insert(0,str(args.idle_checkout))
from redis.asyncio import Redis
from aiogram_idle import IdleConfig
from aiogram_idle.storage.redis import RedisIdleBackend
from aiogram_idle.storage.codec import decode
from aiogram_nav import RenderResult,MessageRef
from tests.test_nav_atomic_recovery import build,KEY
class CountRedis(Redis):
 async def execute_command(self,*args,**kwargs):
  self.counts[str(args[0])]+=1
  return await super().execute_command(*args,**kwargs)
async def main():
 r=CountRedis.from_url(args.redis_url);r.counts=collections.Counter()
 b=RedisIdleBackend(redis=r,prefix="review:combined:"+str(time.time_ns()),config=IdleConfig(enabled=True))
 await b.initialize(); idle,integ,nav,_=build(b);await idle.initialize()
 key=integ.navigation_repository.mapping.to_idle(KEY)
 print("redis",(await r.info("server"))["redis_version"],flush=True)
 for i in range(1,17):
  r.counts.clear();start=time.perf_counter()
  await nav.for_conversation(KEY).track("editor" if i%2 else "main",rendered=RenderResult("view-"+str(i),(MessageRef(42,100+i),)),operation_id="screen-"+str(i))
  elapsed=time.perf_counter()-start;counts=dict(r.counts)
  raw=await r.get(b._store.keys(key)[0]);data=decode(raw.decode())
  if i in (1,2,4,8,12,16):
   sizes=[len(__import__('aiogram_idle.storage.codec',fromlist=['encode']).encode(x)) for x in data['receipts'].values()]
   print(json.dumps(dict(n=i,seconds=round(elapsed,4),commands=sum(counts.values()),counts=counts,bytes=len(raw),receipts=len(sizes),receipt_bytes=sum(sizes),max_receipt_bytes=max(sizes))),flush=True)
 await b.close();await r.aclose()
asyncio.run(main())
