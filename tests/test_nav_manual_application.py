"""Combined installation preserves chosen routing and application-owned rendering."""

import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import CallbackQuery, Update, User
from aiogram_coordination import TrackedEventIsolation

pytest.importorskip("aiogram_nav")
from aiogram_nav import (
    ApplicationPresenter,
    CleanupResult,
    InputBindings,
    MessageRef,
    RenderResult,
    ReplyEntry,
    create_bindings_router,
)

from tests.test_nav_runtime import make
from tests.test_telegram import message
from tests.test_telegram_failures import RecordingSession


async def test_manual_combined_reply_bindings_respect_earlier_state_guard():
    bot = Bot("123456:ABC", session=RecordingSession())
    dispatcher = Dispatcher(events_isolation=TrackedEventIsolation(SimpleEventIsolation()))
    integration, nav, screens, _, key = make(bot=bot)
    nav.bind(
        InputBindings([ReplyEntry("form", "form", target="form", params={"draft_id": "draft"})]),
        translator=lambda key, locale: "Next",
    )
    guarded = Router()
    seen = []

    @guarded.message(StateFilter("typing"), F.text == "Next")
    async def guard(message):
        seen.append(message.text)

    dispatcher.include_router(guarded)
    bindings = create_bindings_router(nav)
    dispatcher.include_router(bindings)
    integration.install(
        dispatcher,
        navigation=nav,
        lifecycle=False,
        bindings_mode="manual",
        bindings_router=bindings,
    )
    context = dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42)
    await context.set_state("typing")
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, message=message("Next")))
        assert seen == ["Next"] and screens.renders == []
        await context.clear()
        await dispatcher.feed_update(bot, Update(update_id=2, message=message("Next", 2)))
        assert screens.renders == ["form"]
        assert (await nav.for_conversation(key).current()).node_id == "form"
        assert dispatcher.sub_routers == [guarded, bindings]
    finally:
        await bot.session.close()
        await dispatcher.emit_shutdown()


async def test_combined_application_prepared_back_uses_only_application_cleanup():
    integration, nav, screens, _, key = make()
    cleanup = []

    async def app_cleanup(request):
        request.ensure_owned()
        cleanup.append(request)
        return CleanupResult()

    nav.presenter = ApplicationPresenter(cleanup=app_cleanup)
    integration.bind(nav)
    context = nav.for_conversation(key)
    for number, (kind, node) in enumerate([("go", "main"), ("go", "form"), ("back", None)], 1):
        prepared = await context.prepare_action(
            kind,
            node_id=node,
            operation_id=str(number),
            params={"draft_id": "draft"} if node == "form" else None,
        )
        await context.complete_render(
            prepared, rendered=RenderResult(prepared.view_id, (MessageRef(42, number),))
        )
    assert screens.renders == [] and len(cleanup) == 3
    assert (await context.current()).node_id == "main"
    record = await integration.idle.inspect(integration.navigation_repository.mapping.to_idle(key))
    assert record.activity.activity_key == "main"


async def test_manual_combined_stale_callback_is_rejected_before_root_handler():
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    dispatcher = Dispatcher()
    integration, nav, _, _, _ = make(bot=bot)
    nav.bind(InputBindings([ReplyEntry("form", "form", target="form")]))
    calls = []

    @dispatcher.callback_query()
    async def intentional(callback):
        calls.append(callback.data)

    bindings = create_bindings_router(nav)
    dispatcher.include_router(bindings)
    integration.install(
        dispatcher,
        navigation=nav,
        lifecycle=False,
        bindings_mode="manual",
        bindings_router=bindings,
        allow_root_handlers=True,
    )
    callback = CallbackQuery(
        id="stale",
        from_user=User(id=42, is_bot=False, first_name="Test"),
        chat_instance="test",
        message=message(),
        data="nav:expired",
    )
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, callback_query=callback))
        assert calls == []
        from aiogram.methods import AnswerCallbackQuery

        assert any(isinstance(call, AnswerCallbackQuery) for call in session.methods)
    finally:
        await bot.session.close()
        await dispatcher.emit_shutdown()
