"""Run the external-authority example through real aiogram without Telegram."""

import logging
import os
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, MessageEntity, Update, User

from tests.test_telegram_failures import RecordingSession

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "external_sessions.py"


def incoming(text, number):
    return Update(
        update_id=number,
        message=Message(
            message_id=number,
            date=datetime.now(timezone.utc),
            text=text,
            chat=Chat(id=42, type="private"),
            from_user=User(id=42, is_bot=False, first_name="Test"),
            entities=[MessageEntity(type="bot_command", offset=0, length=6)]
            if text == "/start"
            else [],
        ),
    )


@pytest.mark.parametrize("fsm", [False, True])
@pytest.mark.parametrize("controls", ["reply", "inline", "commands", "hybrid"])
async def test_external_demo_owns_sessions_and_explicit_activity(fsm, controls):
    module = runpy.run_path(str(EXAMPLE))
    session = RecordingSession()
    bot = Bot("123456:TEST", session=session)
    demo = await module["create_demo"](bot, fsm=fsm, controls=controls)
    try:
        await demo.dispatcher.feed_update(bot, incoming("/start", 1))
        assert len(demo.sessions.sessions) == 1
        original = next(iter(demo.sessions.sessions.values()))
        key = next(iter(demo.flow.drafts))
        first = await demo.runtime.for_conversation(key).current()
        assert first.activity_key == "draft.typing"
        assert first.expires_at * 1000 == original.absolute_expires_at
        assert first.session_id != original.session_id  # Separate recovery generation.
        await demo.dispatcher.feed_update(bot, incoming("Saved content", 2))
        assert demo.flow.drafts[key].text == "Saved content"
        assert next(iter(demo.sessions.sessions.values())) == original
        activity = await demo.runtime.for_conversation(key).current()
        assert activity.activity_revision == first.activity_revision + 1
        if fsm:
            context = demo.dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42)
            assert await context.get_state() == "DraftState:typing"
            assert (await context.get_data())["draft_text"] == "Saved content"
    finally:
        await demo.dispatcher.emit_shutdown()
        await demo.runtime.backend.close()
        await demo.application_isolation.close()
        await bot.session.close()


def test_external_demo_help_without_token_and_safe_import(monkeypatch):
    configured = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: configured.append(kwargs))
    runpy.run_path(str(EXAMPLE))
    assert configured == []
    env = dict(os.environ)
    env.pop("BOT_TOKEN", None)
    result = subprocess.run(
        [sys.executable, str(EXAMPLE), "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0 and "--controls" in result.stdout
