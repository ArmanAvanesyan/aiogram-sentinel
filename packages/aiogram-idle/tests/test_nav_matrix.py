"""Optional combined matrix: actual Telegram shapes and atomic activity ownership."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

pytest.importorskip("aiogram_nav")

from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from aiogram_nav import (
    ConversationKey,
    Navigation,
    NavigationRegistry,
    Node,
    ScreenSpec,
    TextPresenter,
)

from aiogram_idle.clock import ManualClock
from aiogram_idle.config import IdleConfig
from aiogram_idle.controls import ControlContext
from aiogram_idle.errors import ActivityConflict
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_idle.models import Phase
from aiogram_idle.policies import ExemptPolicy, IdlePolicies, PromptPolicy
from aiogram_idle.presentation import TelegramPromptPresenter
from aiogram_idle.runtime import IdleRuntime
from aiogram_idle.storage.memory import MemoryIdleBackend
from tests.runtime_helpers import Adapter
from tests.test_telegram import message


@pytest.fixture(params=["memory", "redis"])
async def combined_backend(request):
    config = IdleConfig(enabled=True)
    client = None
    if request.param == "memory":
        backend = MemoryIdleBackend(clock=ManualClock(), config=config)
    else:
        redis = pytest.importorskip("redis.asyncio")
        url = request.getfixturevalue("redis_url")
        client = redis.Redis.from_url(url)
        from aiogram_idle.storage.redis import RedisIdleBackend

        backend = RedisIdleBackend(
            redis=client, prefix=f"combined-matrix:{uuid4().hex}", config=config
        )
        await backend.initialize()
    yield backend
    await backend.close()
    if client is not None:
        await client.aclose()


@pytest.mark.parametrize("style", ["reply", "inline", "commands", "hybrid"])
async def test_combined_style_atomic_acceptance_and_prompt_controls(combined_backend, style):
    backend = combined_backend
    bot = Bot("123456:ABC")
    sent = []

    async def send(*args, **kwargs):
        sent.append((args, kwargs))
        return message(message_id=100 + len(sent)).model_copy(
            update={"date": datetime.fromtimestamp(backend.clock.now(), timezone.utc)}
        )

    bot.send_message = AsyncMock(side_effect=send)
    bot.edit_message_text = AsyncMock(return_value=message(message_id=999))
    bot.edit_message_reply_markup = AsyncMock(return_value=message(message_id=999))
    bot.answer_callback_query = AsyncMock(return_value=True)
    app = Adapter()
    idle = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"none": ExemptPolicy(), "draft": PromptPolicy(20, 20, style)}),
        adapters={"business": app},
        presenter=TelegramPromptPresenter(bot),
        bot=bot,
    )
    registry = NavigationRegistry(
        roots={"main"},
        nodes=[Node("main", renderer="text"), Node("editor", parent="main", renderer="text")],
    )
    integration = NavigationIntegration(
        idle=idle,
        registry=registry,
        policies=NodePolicies(default="none", overrides={"editor": "draft"}),
        adapters={"editor": app},
    )

    async def screen(request):
        return ScreenSpec(
            "Edit your draft" if request.node_id == "editor" else "Menu",
            inline_keyboard=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="External", url="https://example.com")]]
            )
            if style in {"inline", "hybrid"}
            else None,
            reply_keyboard=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Menu")]])
            if style in {"reply", "hybrid"}
            else None,
            reply_keyboard_key="main" if style in {"reply", "hybrid"} else None,
        )

    nav = Navigation(
        registry=registry,
        repository=integration.navigation_repository,
        presenter=TextPresenter({"text": screen}, bot),
        bot=bot,
    )
    dp = Dispatcher(events_isolation=SimpleEventIsolation())
    integration.install(dp, navigation=nav, lifecycle=False)
    router = Router()

    @router.message()
    async def start(message, nav_context):
        await nav_context.go("editor", params={"draft_id": "draft"})

    dp.include_router(router)
    key = ConversationKey("default", bot.id, 42, 42)
    mapped = integration.navigation_repository.mapping.to_idle(key)
    try:
        await dp.feed_update(bot, Update(update_id=1, message=message("begin")))
        record = await backend.load(mapped)
        current = await nav.for_conversation(key).current()
        assert record.activity.session_id == current.session_id == record.session.session_id
        assert record.activity.activity_revision == current.activity_revision
        assert record.activity.last_activity_at == current.last_activity_at / 1000
        assert record.activity.policy_id == "draft" and record.idle.phase == Phase.ACTIVE
        assert record.idle.deadline == pytest.approx(
            record.activity.last_activity_at + 20, abs=0.002
        )
        with pytest.raises(ActivityConflict):
            await idle.for_conversation(mapped).touch(
                expected=record.activity.guard, operation_id="wrong-writer"
            )
        touched = await integration.touch(key, expected=record.activity.guard, operation_id="text")
        assert touched.activity_revision == current.activity_revision + 1
        # A background navigation update changes view but preserves accepted activity.
        before = await backend.load(mapped)
        await nav.for_conversation(key).go(
            "editor",
            params={"draft_id": "draft"},
            operation_id="background",
            accepted_activity=False,
        )
        after = await backend.load(mapped)
        assert after.activity == before.activity and after.idle.deadline == before.idle.deadline
        # Move only the scheduler deadline so the test does not sleep for policy time.
        await backend.transition(
            mapped,
            expected_version=after.version,
            operation_id="make-due",
            fingerprint="make-due",
            transform=lambda old: replace(
                old, idle=replace(old.idle, deadline=backend.clock.now())
            ),
        )
        await idle.run_once()
        prompted = await backend.load(mapped)
        assert prompted.idle.phase == Phase.PROMPTED
        assert prompted.idle.prompt.controls == style
        question = [
            kwargs
            for args, kwargs in sent
            if kwargs.get("reply_markup") is not None or style == "commands"
        ]
        assert question
        # Explicit prompt controls are reserved before business/navigation inputs.
        result = await idle.continue_current(ControlContext(mapped, 42, operation_id="continue"))
        assert result.accepted
        final = await backend.load(mapped)
        view = await nav.for_conversation(key).current()
        assert final.idle.phase == Phase.ACTIVE, final.idle
        assert final.activity.activity_id == touched.activity_id
        assert final.activity.activity_revision == view.activity_revision
        assert view.node_id == "editor" and view.params["draft_id"] == "draft"
        if style in {"reply", "hybrid"}:
            markup = sent[-1][1].get("reply_markup")
            assert isinstance(markup, ReplyKeyboardMarkup)
            assert markup.keyboard[0][0].text == "Menu"
    finally:
        await dp.fsm.close()
        await bot.session.close()
