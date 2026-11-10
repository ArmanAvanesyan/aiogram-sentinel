"""Exercise runnable example menus through the real Dispatcher pipeline."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, SetMyCommands
from aiogram.types import Chat, Message, MessageEntity, Update, User


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=99,
                date=datetime.now(timezone.utc),
                chat=Chat(id=42, type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, url, **kwargs):
        yield b""


def load_example(name):
    path = Path(__file__).parents[2] / "examples" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command_update(text, update_id):
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=42, type="private"),
            from_user=User(id=42, first_name="Example", is_bot=False),
            text=text,
            entities=[MessageEntity(type="bot_command", offset=0, length=len(text))],
        ),
    )


@pytest.mark.parametrize(
    ("name", "commands", "expected"),
    [
        ("basic_bot", ["/start"], None),
        ("profile_based_bot", ["/join", "/profile"], ["start", "profile"]),
        ("dynamic_bot", ["/start", "/finish"], ["start"]),
    ],
)
async def test_example_handlers_use_real_profiles_without_network(
    name, commands, expected
):
    module = load_example(name)  # No token, logging configuration or network on import.
    session = RecordingSession()
    bot = Bot("123456:TEST", session=session)
    try:
        dp = module.create_dispatcher(bot)
        await dp.emit_startup()
        for index, text in enumerate(commands, 1):
            await dp.feed_update(bot, command_update(text, index))
        menus = [call for call in session.calls if isinstance(call, SetMyCommands)]
        assert menus
        if expected is not None:
            assert [command.command for command in menus[-1].commands] == expected
            assert menus[-1].scope.type == "chat"
            assert menus[-1].scope.chat_id == 42
        replies = [call.text for call in session.calls if isinstance(call, SendMessage)]
        assert len(replies) == len(commands)
        if name == "profile_based_bot":
            assert replies[-1] == "Demo member"
        await dp.emit_shutdown()
    finally:
        await session.close()


async def test_gettext_example_registers_translated_menus(tmp_path):
    pofile = pytest.importorskip("babel.messages.pofile")
    mofile = pytest.importorskip("babel.messages.mofile")
    module = load_example("i18n_bot")
    source = Path(module.__file__).parent
    for locale in ("en", "ru", "es"):
        target = tmp_path / "locales" / locale / "LC_MESSAGES" / "messages.mo"
        target.parent.mkdir(parents=True)
        with (source / "locales" / locale / "LC_MESSAGES" / "messages.po").open() as po:
            catalog = pofile.read_po(po)
        with target.open("wb") as mo:
            mofile.write_mo(mo, catalog)
    module.__file__ = str(tmp_path / "i18n_bot.py")
    session = RecordingSession()
    bot = Bot("123456:TEST", session=session)
    try:
        dp = module.create_dispatcher(bot)
        await dp.emit_startup()
        menus = [call for call in session.calls if isinstance(call, SetMyCommands)]
        assert {call.language_code for call in menus} >= {"en", "ru", "es"}
        english = next(call for call in menus if call.language_code == "en")
        assert english.commands[0].description == "Start the bot"
        await dp.feed_update(bot, command_update("/start", 1))
        assert "Hello Example" in session.calls[-1].text
        await dp.emit_shutdown()
    finally:
        await session.close()
