"""A reply prompt invalidates the navigation tray's former installation proof."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("aiogram_nav")

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram_nav import (
    ConversationKey,
    Navigation,
    NavigationRegistry,
    Node,
    ScreenSpec,
    TextPresenter,
)

from aiogram_idle.controls import ControlContext
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_idle.models import Phase
from aiogram_idle.policies import ExemptPolicy, IdlePolicies, PromptPolicy
from aiogram_idle.presentation import TelegramPromptPresenter
from aiogram_idle.runtime import IdleRuntime
from tests.runtime_helpers import Adapter
from tests.test_nav_matrix import combined_backend  # noqa: F401 -- shared backend parity fixture
from tests.test_telegram import message


@pytest.mark.parametrize("style", ["reply", "hybrid"])
@pytest.mark.parametrize(
    "answer,destination",
    [("continue", "keyboard"), ("cancel", "keyboard"), ("cancel", "remove"), ("cancel", "omit")],
)
async def test_staged_answer_reinstalls_or_removes_actual_prompt_reply_tray(
    combined_backend,  # noqa: F811 -- imported parity fixture
    style,
    answer,
    destination,
):
    backend = combined_backend
    bot = Bot("123456:ABC")
    sent = []

    async def send(*args, **kwargs):
        sent.append(kwargs)
        return message(message_id=100 + len(sent)).model_copy(
            update={"date": datetime.fromtimestamp(backend.clock.now(), timezone.utc)}
        )

    bot.send_message = AsyncMock(side_effect=send)
    bot.edit_message_text = AsyncMock(return_value=message(message_id=999))
    bot.edit_message_reply_markup = AsyncMock(return_value=True)

    class OverlayPresenter(TelegramPromptPresenter):
        async def show(self, request):
            if request.controls == "hybrid":
                request = replace(
                    request,
                    reply_keyboard=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="Continue"), KeyboardButton(text="Cancel")]]
                    ),
                )
            return await super().show(request)

    idle = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"none": ExemptPolicy(), "draft": PromptPolicy(20, 20, style)}),
        adapters={"placeholder": Adapter()},
        presenter=OverlayPresenter(bot),
        bot=bot,
    )
    registry = NavigationRegistry(
        roots={"main"},
        nodes=[
            Node("main", renderer="text"),
            Node("editor", parent="main", renderer="text"),
        ],
    )
    integration = NavigationIntegration(
        idle=idle,
        registry=registry,
        policies=NodePolicies(default="none", overrides={"editor": "draft"}),
    )

    async def screen(request):
        remove = request.node_id == "main" and destination == "remove"
        omit = request.node_id == "main" and destination == "omit"
        return ScreenSpec(
            request.node_id,
            inline_keyboard=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="External", url="https://example.com")]]
            )
            if style == "hybrid"
            else None,
            reply_keyboard=None
            if omit
            else ReplyKeyboardRemove()
            if remove
            else ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Menu")]]),
            reply_keyboard_key=None if remove or omit else "main",
        )

    nav = Navigation(
        registry=registry,
        repository=integration.navigation_repository,
        presenter=TextPresenter({"text": screen}, bot),
        bot=bot,
    )
    integration.bind(nav)
    key = ConversationKey("default", bot.id, 42, 42)
    mapped = integration.navigation_repository.mapping.to_idle(key)
    try:
        await nav.for_conversation(key).go(
            "editor", params={"draft_id": "draft"}, operation_id="entry"
        )
        before = await backend.load(mapped)
        assert (await nav.for_conversation(key).current()).view.reply_keyboard_key == "main"
        await backend.transition(
            mapped,
            expected_version=before.version,
            operation_id="due",
            fingerprint="due",
            transform=lambda old: replace(
                old, idle=replace(old.idle, deadline=backend.clock.now())
            ),
        )
        assert (await idle.run_once()).completed == 1
        assert (await backend.load(mapped)).idle.phase is Phase.PROMPTED
        assert any(
            isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup)
            and kwargs["reply_markup"].keyboard[0][0].text == "Continue"
            for kwargs in sent
        )
        sent.clear()
        function = idle.continue_current if answer == "continue" else idle.cancel_current
        assert (await function(ControlContext(mapped, 42, operation_id="answer"))).accepted
        if answer == "cancel":
            assert sent and all(kwargs.get("disable_notification") is True for kwargs in sent)
        current = await nav.for_conversation(key).current()
        expected = "editor" if answer == "continue" else "main"
        assert current.node_id == expected
        if destination in {"remove", "omit"}:
            assert any(
                isinstance(kwargs.get("reply_markup"), ReplyKeyboardRemove) for kwargs in sent
            )
            assert current.view.reply_keyboard_key is None
        else:
            actual = [kwargs.get("reply_markup") for kwargs in sent]
            assert any(
                isinstance(markup, ReplyKeyboardMarkup) and markup.keyboard[0][0].text == "Menu"
                for markup in actual
            )
            assert current.view.reply_keyboard_key == "main"
        after = await backend.load(mapped)
        assert after.idle.operation is None
        assert current.activity_revision == after.activity.activity_revision
        assert after.idle.phase is (Phase.ACTIVE if answer == "continue" else Phase.DISARMED)
    finally:
        await bot.session.close()
