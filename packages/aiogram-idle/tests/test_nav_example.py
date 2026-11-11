"""Exercise the runnable optional example through real Dispatcher routing."""

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("aiogram_nav")

from aiogram import Bot, Dispatcher
from aiogram.types import Update

from tests.test_telegram import message


@pytest.mark.parametrize("style", ["reply", "inline", "commands", "hybrid"])
async def test_navigation_example_routes_form_without_telegram(monkeypatch, style):
    import examples.navigation as demo

    bot = Bot("123456:ABC")
    sent = []

    async def send(*args, **kwargs):
        sent.append((args, kwargs))
        return message(message_id=100 + len(sent)).model_copy(
            update={"date": datetime.now(timezone.utc)}
        )

    bot.send_message = AsyncMock(side_effect=send)
    bot.edit_message_text = AsyncMock(return_value=message(message_id=999))
    bot.edit_message_reply_markup = AsyncMock(return_value=message(message_id=999))
    bot.answer_callback_query = AsyncMock(return_value=True)
    monkeypatch.setattr(demo, "Bot", lambda token: bot)
    monkeypatch.setenv("BOT_TOKEN", "123456:ABC")
    monkeypatch.delenv("NAV_REDIS_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["navigation.py", "--style", style])
    configured = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: configured.append(kwargs))

    async def polling(dispatcher, *bots, **kwargs):
        await dispatcher.feed_update(bot, Update(update_id=1, message=message("/form")))
        await dispatcher.feed_update(bot, Update(update_id=2, message=message("accepted input")))
        assert sent
        assert "form:" in sent[0][0][1]

    monkeypatch.setattr(Dispatcher, "start_polling", polling)
    await demo.main()
    assert configured[0]["level"] == logging.INFO


def test_navigation_help_does_not_require_a_bot_token() -> None:
    env = dict(os.environ)
    env.pop("BOT_TOKEN", None)
    example = Path(__file__).resolve().parents[1] / "examples" / "navigation.py"
    result = subprocess.run(
        [sys.executable, str(example), "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "--style" in result.stdout
