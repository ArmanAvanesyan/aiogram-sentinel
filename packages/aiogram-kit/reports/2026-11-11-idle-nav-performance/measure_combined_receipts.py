import asyncio, sys, time
from types import SimpleNamespace
sys.path.insert(0,'/Users/armanavanesyan/oss/own/aiogram-idle')
from tests.test_nav_projection import integrated, KEY
from aiogram_nav import RenderResult
from aiogram_idle.storage.codec import encode

async def main():
    fixture=integrated.__wrapped__(SimpleNamespace(param='memory'))
    integration,nav,backend,presenter=await anext(fixture)
    idle_key=integration.navigation_repository.key_to_idle(KEY)
    start=time.perf_counter()
    try:
        for i in range(1,66):
            try:
                await nav.for_conversation(KEY).track('form',rendered=RenderResult(f'view-{i}'),operation_id=f'track-{i}')
            except Exception as e:
                print('failure',i,type(e).__name__,str(e));break
            if i in [1,4,8,16,32,48,64]:
                record=await backend.load(idle_key)
                receipts=backend._receipts.items[idle_key]
                print(i,'receipts',len(receipts),'component-bytes',len(str(record.components['aiogram_nav']['ledger'])),'receipt-bytes',len(encode(receipts)),'elapsed',round(time.perf_counter()-start,3))
    finally:
        await fixture.aclose()
asyncio.run(main())
