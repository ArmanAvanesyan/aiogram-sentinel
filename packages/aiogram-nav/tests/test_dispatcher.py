"""Dispatcher isolation, explicit binding precedence and token ownership."""

import asyncio

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Update, User

from aiogram_nav import (
    CommandEntry,
    ConfigurationError,
    ConversationKey,
    InputBindings,
    MemoryNavigationRepository,
    Navigation,
    NavigationRegistry,
    Node,
    PersistenceUnavailable,
    ScreenSpec,
    TextPresenter,
)
from examples.demo import build_demo, parse_args
from tests.test_examples import ACTOR, BOT_USER, RecordingSession, incoming


def harness(*, isolated=False, disable_fsm=False, bindings=None):
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    dispatcher = Dispatcher(
        events_isolation=SimpleEventIsolation() if isolated else None, disable_fsm=disable_fsm
    )

    async def screen(request):
        return ScreenSpec(request.node_id)

    navigation = Navigation(
        registry=NavigationRegistry(
            roots={"main"},
            nodes=[
                Node("main", renderer="screen"),
                Node("panel", parent="main", renderer="screen"),
            ],
        ),
        repository=MemoryNavigationRepository(),
        presenter=TextPresenter({"screen": screen}, bot),
        bindings=bindings,
    )
    return dispatcher, navigation, bot, session


@pytest.mark.parametrize("isolated,disable_fsm", [(False, False), (True, False), (True, True)])
async def test_entire_business_handler_and_direct_action_share_one_lock(isolated, disable_fsm):
    dispatcher, nav, bot, _ = harness(isolated=isolated, disable_fsm=disable_fsm)
    nav.install(dispatcher)
    app = Router()
    entered, release = asyncio.Event(), asyncio.Event()

    @app.message()
    async def business(message, nav_context):
        assert nav.coordinator.scope_token(nav_context.key) is not None
        entered.set()
        await release.wait()

    dispatcher.include_router(app)
    key = ConversationKey(nav.namespace, bot.id, 42, 42)
    update = asyncio.create_task(
        dispatcher.feed_update(bot, Update(update_id=1, message=incoming("slow")))
    )
    action = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        action = asyncio.create_task(nav.for_conversation(key).go("main", operation_id="other"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not action.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(update, action), timeout=5)
    finally:
        release.set()
        update.cancel()
        if action:
            action.cancel()
        await asyncio.gather(update, *([action] if action else []), return_exceptions=True)
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_invalid_root_observer_installation_does_not_mutate_dispatcher():
    dispatcher, nav, bot, _ = harness(
        isolated=True, bindings=InputBindings([CommandEntry("main", command="menu", target="main")])
    )

    @dispatcher.message()
    async def root_handler(message):
        pass

    original = list(dispatcher.update.outer_middleware)
    coordinator = nav.coordinator
    try:
        with pytest.raises(ConfigurationError):
            nav.install(dispatcher)
        assert list(dispatcher.update.outer_middleware) == original
        assert nav.coordinator is coordinator
        assert not dispatcher.get("_aiogram_nav_installed")
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_duplicate_install_and_later_binding_changes_are_rejected():
    dispatcher, nav, bot, _ = harness()
    nav.install(dispatcher)
    try:
        with pytest.raises(ConfigurationError):
            nav.install(dispatcher)
        with pytest.raises(ConfigurationError):
            nav.bind(InputBindings([]))
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


@pytest.mark.parametrize("mutation", ["remove", "replace", "reorder"])
async def test_changed_fsm_cannot_be_borrowed(mutation):
    dispatcher, nav, bot, _ = harness(isolated=True)
    nav.install(dispatcher)
    items = dispatcher.update.outer_middleware
    if mutation == "replace":
        dispatcher.fsm.events_isolation = SimpleEventIsolation()
    elif mutation == "remove":
        items.unregister(dispatcher.fsm)
    else:
        items.unregister(dispatcher.fsm)
        items.register(dispatcher.fsm)
    try:
        with pytest.raises(ConfigurationError):
            await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("hello")))
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_callback_retry_after_consumption_uses_same_logical_action():
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    dispatcher, nav = build_demo(bot, parse_args(["--style", "inline"]))
    key = ConversationKey(nav.namespace, bot.id, 42, 42)
    await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("/start")))
    current = await nav.for_conversation(key).current()
    data = next(
        method.reply_markup.inline_keyboard[0][0].callback_data
        for method in session.methods
        if isinstance(method, SendMessage) and method.reply_markup is not None
    )
    original = nav.perform

    async def fail_before_prepare(*args, **kwargs):
        raise PersistenceUnavailable("injected before prepare")

    nav.perform = fail_before_prepare
    callback = CallbackQuery(
        id="one",
        from_user=ACTOR,
        chat_instance="test",
        message=incoming("screen", current.view.messages[0].message_id).model_copy(
            update={"from_user": BOT_USER}
        ),
        data=data,
    )
    try:
        with pytest.raises(PersistenceUnavailable):
            await dispatcher.feed_update(bot, Update(update_id=2, callback_query=callback))
        nav.perform = original
        await dispatcher.feed_update(
            bot, Update(update_id=3, callback_query=callback.model_copy(update={"id": "two"}))
        )
        assert (await nav.for_conversation(key).current()).node_id == "panel"
        revision = (await nav.for_conversation(key).current()).nav_revision
        await dispatcher.feed_update(
            bot, Update(update_id=4, callback_query=callback.model_copy(update={"id": "stale"}))
        )
        assert (await nav.for_conversation(key).current()).nav_revision == revision
        assert any(
            isinstance(method, AnswerCallbackQuery) and method.text for method in session.methods
        )
    finally:
        nav.perform = original
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_actor_spoof_callback_is_acknowledged_without_mutation():
    dispatcher, nav, bot, session = harness(bindings=InputBindings([]))
    nav.install(dispatcher)
    callback = CallbackQuery(
        id="spoof",
        from_user=User(id=43, is_bot=False, first_name="Other"),
        chat_instance="test",
        message=incoming("screen").model_copy(update={"from_user": BOT_USER}),
        data="nav:AAAAAAAAAAAAAAAAAAAA",
    )
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, callback_query=callback))
        assert len(session.methods) == 1 and isinstance(session.methods[0], AnswerCallbackQuery)
        assert await nav.repository.load(ConversationKey(nav.namespace, bot.id, 42, 42)) is None
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
