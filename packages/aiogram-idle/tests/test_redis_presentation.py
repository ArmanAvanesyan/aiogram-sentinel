"""Standalone Redis runtime supports all prompt transports, without navigation."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from aiogram import Dispatcher
from aiogram.types import Update

from aiogram_idle import IdleConfig, IdlePolicies, IdleRuntime, PromptPolicy
from aiogram_idle.presentation import TelegramPromptPresenter
from aiogram_idle.storage.redis import RedisIdleBackend
from tests.runtime_helpers import Adapter
from tests.test_redis_backend import make_due
from tests.test_telegram import KEY, message
from tests.test_telegram import bot as telegram_bot  # noqa: F401 -- fixture


@pytest.mark.parametrize("style", ["reply", "inline", "commands", "hybrid"])
async def test_redis_prompt_transport_and_dispatcher_answer(redis_client, telegram_bot, style):  # noqa: F811
    bot = telegram_bot
    backend = RedisIdleBackend(
        redis=redis_client,
        prefix=f"test-presentation:{uuid4().hex}",
        config=IdleConfig(enabled=True),
    )
    await backend.initialize()
    bot.send_message.return_value = message(message_id=99).model_copy(
        update={"date": datetime.fromtimestamp(backend.clock.now(), timezone.utc)}
    )
    adapter = Adapter()
    runtime = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"draft": PromptPolicy(10, 20, controls=style)}),
        adapters={"form": adapter},
        presenter=TelegramPromptPresenter(bot),
    )
    await runtime.initialize()
    context = runtime.for_conversation(KEY)
    session = await context.open_session(lifetime_seconds=300, operation_id="open")
    await context.enter(
        "form",
        policy_id="draft",
        adapter_key="form",
        params={"draft_id": "draft"},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
    )
    await make_due(backend, KEY)
    await runtime.run_once()
    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count == 0
    dispatcher = Dispatcher()
    runtime.install(dispatcher, lifecycle=False)
    prompt = await runtime.current_prompt(KEY)
    assert prompt is not None
    if style in {"inline", "hybrid"}:
        from aiogram.types import CallbackQuery

        event = Update(
            update_id=7,
            callback_query=CallbackQuery(
                id="answer",
                from_user=message().from_user,
                chat_instance="test",
                message=message(message_id=99),
                data=f"idle:c:{prompt.continue_token}",
            ),
        )
    else:
        event = Update(
            update_id=7,
            message=message("Continue" if style == "reply" else "/continue", message_id=100),
        )
    try:
        await dispatcher.feed_update(bot, event)
        assert adapter.calls.count("resume") == 1
        assert bot.edit_message_text.await_count == 1
        assert (await context.current()).activity_key == "form"
    finally:
        await dispatcher.fsm.close()
        await backend.close()
        await bot.session.close()
