"""Runnable examples use actual Dispatcher updates and a recording Telegram transport."""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    GetMe,
    SendMessage,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    Update,
    User,
)

from aiogram_nav.models import ConversationKey
from examples.demo import DraftFlow, build_demo, parse_args

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
ACTOR = User(id=42, is_bot=False, first_name="Example")
BOT_USER = User(id=123456, is_bot=True, first_name="Navigation", username="navigation_demo_bot")


def incoming(text, message_id=10):
    return Message(
        message_id=message_id,
        date=NOW,
        chat=Chat(id=42, type="private"),
        from_user=ACTOR,
        text=text,
    )


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.methods = []
        self.sequence = 0

    async def close(self):
        pass

    async def stream_content(
        self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True
    ):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, (AnswerCallbackQuery, EditMessageReplyMarkup)):
            return True
        if isinstance(method, (SendMessage, EditMessageText)):
            self.sequence += 1
            return Message(
                message_id=getattr(method, "message_id", None) or self.sequence,
                date=NOW,
                chat=Chat(id=int(method.chat_id), type="private"),
                from_user=BOT_USER,
                text=method.text,
            )
        raise AssertionError(f"Unexpected Telegram method: {type(method).__name__}")


@pytest.mark.parametrize("style", ["reply", "inline", "commands", "hybrid"])
@pytest.mark.parametrize("fsm", [False, True])
async def test_demo_styles_and_owned_draft_cancellation(style, fsm):
    args = parse_args(["--style", style] + (["--fsm"] if fsm else []))
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    dispatcher, navigation = build_demo(bot, args)
    key = ConversationKey(navigation.namespace, bot.id, 42, 42)
    context = navigation.for_conversation(key)
    state = dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42)
    await state.update_data(unrelated="preserve")
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, message=incoming("/start")))
        assert (await context.current()).node_id == "main"
        sends = [method for method in session.methods if isinstance(method, SendMessage)]
        markups = [method.reply_markup for method in sends]
        if style == "commands":
            assert all(markup is None for markup in markups)
        elif style == "reply":
            assert any(isinstance(markup, ReplyKeyboardMarkup) for markup in markups)
            assert not any(isinstance(markup, InlineKeyboardMarkup) for markup in markups)
        elif style == "inline":
            assert any(isinstance(markup, InlineKeyboardMarkup) for markup in markups)
            assert not any(isinstance(markup, ReplyKeyboardMarkup) for markup in markups)
        else:
            assert any(isinstance(markup, InlineKeyboardMarkup) for markup in markups)
            assert any(isinstance(markup, ReplyKeyboardMarkup) for markup in markups)
        if style in {"reply", "commands"}:
            event = Update(
                update_id=2, message=incoming("Edit draft" if style == "reply" else "/edit")
            )
        else:
            content = next(
                method for method in sends if isinstance(method.reply_markup, InlineKeyboardMarkup)
            )
            data = content.reply_markup.inline_keyboard[1][0].callback_data
            displayed = (await context.current()).view.messages[0]
            event = Update(
                update_id=2,
                callback_query=CallbackQuery(
                    id="edit",
                    from_user=ACTOR,
                    chat_instance="example",
                    message=Message(
                        message_id=displayed.message_id,
                        date=NOW,
                        chat=Chat(id=42, type="private"),
                        from_user=BOT_USER,
                    ),
                    data=data,
                ),
            )
        await dispatcher.feed_update(bot, event)
        assert (await context.current()).node_id == "editor"
        await dispatcher.feed_update(bot, Update(update_id=3, message=incoming("a draft", 11)))
        if fsm:
            assert await state.get_state() == DraftFlow.typing.state
            assert (await state.get_data())["demo_draft"] == "a draft"
        await context.back(operation_id="test:back")
        assert (await context.current()).node_id == "main"
        if fsm:
            assert (await state.get_data())["demo_draft"] == "a draft"
        await context.go("editor", operation_id="test:reenter")
        assert any(
            "7 saved characters" in method.text
            for method in session.methods
            if isinstance(method, (SendMessage, EditMessageText))
        )
        await context.cancel(operation_id="test:cancel")
        assert (await context.current()).node_id == "main"
        assert (await state.get_data())["unrelated"] == "preserve"
        if fsm:
            assert await state.get_state() is None
            assert "demo_draft" not in await state.get_data()
        await dispatcher.feed_update(bot, Update(update_id=4, message=incoming("/status", 12)))
        assert "saved characters: 0" in session.methods[-1].text
    finally:
        await navigation.repository.close()
        await dispatcher.fsm.close()
        await bot.session.close()


def test_all_example_entry_points_have_token_free_help():
    env = dict(os.environ)
    env.pop("BOT_TOKEN", None)
    commands = [["examples/demo.py"]] + [
        ["-m", f"examples.{name}.main"]
        for name in ("reply_only", "inline_only", "commands_only", "hybrid")
    ]
    for arguments in commands:
        result = subprocess.run(
            [sys.executable, *arguments, "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
        assert "--style" in result.stdout
