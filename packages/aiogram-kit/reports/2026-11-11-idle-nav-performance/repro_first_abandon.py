import asyncio,sys
from types import SimpleNamespace
sys.path.insert(0,'/Users/armanavanesyan/oss/own/aiogram-idle')
from tests.test_nav_projection import integrated,KEY
async def main():
    fixture=integrated.__wrapped__(SimpleNamespace(param='memory'))
    integration,nav,backend,_=await anext(fixture)
    try:
        prepared=await nav.for_conversation(KEY).prepare_render('form',operation_id='first')
        try:
            await nav.repository.abandon(KEY,'first',expected_session_id=prepared.session_id)
        except Exception as e:
            print(type(e).__name__,str(e))
        print('pending afterwards:',(await nav.repository.pending(KEY)).operation_id)
    finally:await fixture.aclose()
asyncio.run(main())
