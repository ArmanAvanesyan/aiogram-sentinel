"""Redis callback provenance and protected handlers through real feed_update."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery
from aiogram.types import CallbackQuery, Update, User

from aiogram_nav import CallbackEntry, InputBindings
from aiogram_nav.models import NavigationAction, NavigationToken
from tests.test_examples import ACTOR, BOT_USER, RecordingSession, incoming
from tests.test_navigation import Presenter
from tests.test_redis_backend import KEY
from tests.test_redis_recovery import navigation, repository


@pytest.mark.parametrize("enabled_fsm", [False, True])
async def test_redis_callback_actor_view_and_retry_ownership(nav_redis_client, enabled_fsm):
    bot = Bot("123456:ABC", session=RecordingSession())
    dispatcher = Dispatcher(
        events_isolation=SimpleEventIsolation() if enabled_fsm else None,
        disable_fsm=not enabled_fsm,
    )
    prefix = f"test:nav:{uuid4().hex}"
    repo = await repository(nav_redis_client, prefix)
    nav = navigation(repo, Presenter())
    key = replace(KEY, bot_id=bot.id)
    context = nav.for_conversation(key)
    try:
        await context.go("main", operation_id="main")
        current = await context.current()
        token = NavigationToken(
            "A" * 24,
            key,
            42,
            current.session_id,
            current.view.view_id,
            NavigationAction(target="panel"),
            current.expires_at,
        )
        await repo.reserve_token(key, token, operation_id="reserve")
        # Reconstruct the runtime before consuming the persisted callback.
        nav = navigation(await repository(nav_redis_client, prefix), Presenter())
        nav.bind(InputBindings([CallbackEntry("panel", "panel", target="panel")]))
        nav.install(dispatcher)
        callback = CallbackQuery(
            id="control",
            from_user=ACTOR,
            chat_instance="test",
            message=incoming("screen", current.view.messages[0].message_id).model_copy(
                update={"from_user": BOT_USER}
            ),
            data=f"nav:{token.token}",
        )
        spoof = callback.model_copy(
            update={"from_user": User(id=43, is_bot=False, first_name="Other")}
        )
        await dispatcher.feed_update(bot, Update(update_id=1, callback_query=spoof))
        assert (await context.current()).node_id == "main"
        await dispatcher.feed_update(bot, Update(update_id=2, callback_query=callback))
        assert (await context.current()).node_id == "panel"
        revision = (await context.current()).nav_revision
        await dispatcher.feed_update(
            bot, Update(update_id=3, callback_query=callback.model_copy(update={"id": "stale"}))
        )
        assert (await context.current()).nav_revision == revision
        assert sum(isinstance(method, AnswerCallbackQuery) for method in bot.session.methods) == 3
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


@pytest.mark.parametrize("enabled_fsm", [False, True])
async def test_redis_handler_state_changes_block_other_replica_navigation(
    nav_redis_client, nav_redis_url, enabled_fsm
):
    from redis.asyncio import Redis

    bot = Bot("123456:ABC", session=RecordingSession())
    dispatcher = Dispatcher(
        events_isolation=SimpleEventIsolation() if enabled_fsm else None,
        disable_fsm=not enabled_fsm,
    )
    prefix = f"test:nav:{uuid4().hex}"
    repo = await repository(nav_redis_client, prefix)
    nav = navigation(repo, Presenter())
    nav.bind(InputBindings([]))
    nav.install(dispatcher)
    client = Redis.from_url(nav_redis_url)
    other = navigation(await repository(client, prefix), Presenter())
    entered, release = asyncio.Event(), asyncio.Event()
    application = Router()
    state = []

    @application.message()
    async def handler(message, nav_context):
        state.append("started")
        entered.set()
        await release.wait()
        state.append("finished")

    dispatcher.include_router(application)
    task = asyncio.create_task(
        dispatcher.feed_update(bot, Update(update_id=1, message=incoming("business")))
    )
    action = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        action = asyncio.create_task(
            other.for_conversation(replace(KEY, bot_id=bot.id)).go(
                "main", operation_id="other-replica"
            )
        )
        await asyncio.sleep(0.05)
        assert not action.done() and state == ["started"]
        release.set()
        await asyncio.wait_for(asyncio.gather(task, action), 5)
        assert state == ["started", "finished"]
    finally:
        release.set()
        task.cancel()
        if action:
            action.cancel()
        await asyncio.gather(task, *([action] if action else []), return_exceptions=True)
        await client.aclose()
        await dispatcher.fsm.close()
        await bot.session.close()
