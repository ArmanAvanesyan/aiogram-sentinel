"""Review regressions for request constraints, plan integrity and binding scope."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from aiogram_nav.errors import ConfigurationError
from aiogram_nav.inputs import CommandEntry, ReplyEntry
from aiogram_nav.models import MessageRef, ViewState
from aiogram_nav.rendering import ScreenSpec
from tests.test_presentation import bot as telegram_bot  # noqa: F401 -- fixture
from tests.test_presentation import inline, render_spec, request


async def test_explicit_refresh_send_cannot_be_overridden_by_screen_edit(telegram_bot):  # noqa: F811
    previous = ViewState("old", (MessageRef(42, 5),), None, "en")
    req = request(telegram_bot, previous=previous, delivery="send")
    result = await render_spec(
        telegram_bot, ScreenSpec("New view", inline_keyboard=inline(), delivery="edit"), req
    )
    assert telegram_bot.edit_message_text.await_count == 0
    assert telegram_bot.send_message.await_count == 1
    assert result.messages[0].message_id != 5


async def test_explicit_request_edit_wins_over_screen_send(telegram_bot):  # noqa: F811
    previous = ViewState("old", (MessageRef(42, 5),), None, "en")
    req = request(telegram_bot, previous=previous, delivery="edit")
    result = await render_spec(telegram_bot, ScreenSpec("Same view", delivery="send"), req)
    assert telegram_bot.edit_message_text.await_count == 1
    assert telegram_bot.send_message.await_count == 0
    assert result.messages[0].message_id == 5


@pytest.mark.parametrize("invalid", [False, [], ""])
async def test_falsey_invalid_inline_plan_is_not_silently_discarded(telegram_bot, invalid):  # noqa: F811
    req = request(telegram_bot)
    await render_spec(telegram_bot, ScreenSpec("Initial"), req)
    req.effects.results["text.plan"] = {**req.effects.results["text.plan"], "inline": invalid}
    before = telegram_bot.send_message.await_count
    with pytest.raises((ConfigurationError, ValidationError)):
        await render_spec(telegram_bot, ScreenSpec("Ignored"), replace(req, view_id="other"))
    assert telegram_bot.send_message.await_count == before


async def test_keep_reply_plan_cannot_hide_removal_markup(telegram_bot):  # noqa: F811
    req = request(telegram_bot)
    await render_spec(telegram_bot, ScreenSpec("Initial"), req)
    req.effects.results["text.plan"] = {
        **req.effects.results["text.plan"],
        "reply": {"remove_keyboard": True},
    }
    with pytest.raises(ConfigurationError):
        await render_spec(telegram_bot, ScreenSpec("Ignored"), req)
    assert telegram_bot.send_message.await_count == 1


@pytest.mark.parametrize("kind", [CommandEntry, ReplyEntry])
@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_global_entry_flag_must_be_boolean(kind, value):
    kwargs = {"command": "home"} if kind is CommandEntry else {"text_key": "Home"}
    with pytest.raises(ConfigurationError):
        kind("home", action="home", global_action=value, **kwargs)


def test_invalid_command_decoder_is_rejected_during_setup():
    with pytest.raises(ConfigurationError):
        CommandEntry("entry", command="open", target="main", decoder=1)


def test_nontext_command_is_typed_configuration_error():
    with pytest.raises(ConfigurationError):
        CommandEntry("entry", command=1, target="main")


@pytest.mark.parametrize(
    "receipt",
    [
        {"chat_id": 42.5, "message_id": 7},
        {"chat_id": 42, "message_id": True},
        {"chat_id": 43, "message_id": 7},
        {"chat_id": "42", "message_id": 7},
    ],
)
async def test_invalid_cached_message_receipt_blocks_following_effects(telegram_bot, receipt):  # noqa: F811
    req = request(telegram_bot)
    req.effects.results["text.content"] = receipt
    from tests.test_presentation import reply

    with pytest.raises(ConfigurationError):
        await render_spec(
            telegram_bot,
            ScreenSpec(
                "Hybrid",
                inline_keyboard=inline(),
                reply_keyboard=reply(),
                reply_keyboard_key="main",
            ),
            req,
        )
    assert telegram_bot.send_message.await_count == 0
    assert telegram_bot.edit_message_text.await_count == 0


async def test_malformed_edit_rejection_does_not_authorize_a_fallback_send(telegram_bot):  # noqa: F811
    previous = ViewState("old", (MessageRef(42, 5),), None, "en")
    req = request(telegram_bot, previous=previous)
    req.effects.results["text.edit"] = {"unavailable": True, "message_id": 5}
    with pytest.raises(ConfigurationError):
        await render_spec(telegram_bot, ScreenSpec("New"), req)
    assert telegram_bot.send_message.await_count == 0
    assert telegram_bot.edit_message_text.await_count == 0
