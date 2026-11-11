"""Telegram call shapes and partial-render recovery use recording bot methods."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import (
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from aiogram_nav.errors import ConfigurationError, RenderFailed, RenderUnknown
from aiogram_nav.models import (
    ConversationKey,
    MessageRef,
    NavigationSnapshot,
    Node,
    RenderRequest,
    ViewState,
)
from aiogram_nav.rendering import CleanupRequest, ScreenSpec, TextPresenter

KEY = ConversationKey("test", 1, 42, 42)


class Ledger:
    def __init__(self):
        self.results = {}
        self.started = set()

    async def run(self, stage, callback, *, replay_safe=False):
        if stage in self.results:
            return self.results[stage]
        if stage in self.started and not replay_safe:
            raise RenderUnknown("Unknown send")
        self.started.add(stage)
        try:
            value = await callback()
        except TelegramRetryAfter:
            self.started.discard(stage)
            raise
        self.started.discard(stage)
        self.results[stage] = value
        return value


@pytest_asyncio.fixture
async def bot():
    value = Bot("1:ABC")
    next_id = 10

    async def send(*args, **kwargs):
        nonlocal next_id
        next_id += 1
        return Message(
            message_id=next_id,
            chat=Chat(id=42, type="private"),
            date=datetime.now(timezone.utc),
            text=args[1] if len(args) > 1 else kwargs["text"],
        )

    value.send_message = AsyncMock(side_effect=send)
    value.edit_message_text = AsyncMock(return_value=True)
    value.edit_message_reply_markup = AsyncMock(return_value=True)
    yield value
    await value.session.close()


def reply():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Home")]])


def inline():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open", callback_data="nav:opaque-token-value")]
        ]
    )


def request(bot, *, previous=None, locale="en", ledger=None, delivery="auto"):
    current = (
        None
        if previous is None
        else NavigationSnapshot("session", "main", {}, 1, 1, 1000, 1000, 10000, previous)
    )
    return RenderRequest(
        key=KEY,
        operation_id="operation",
        node=Node("main", renderer="main"),
        params={},
        view_id="new",
        session_id="session",
        current=current,
        locale=locale,
        bot=bot,
        effects=ledger or Ledger(),
        delivery=delivery,
    )


async def render_spec(bot, spec, req=None):
    async def renderer(request):
        return spec

    return await TextPresenter({"main": renderer}, bot).render(req or request(bot))


@pytest.mark.parametrize("style", ["reply", "inline", "commands", "hybrid"])
async def test_four_styles_have_valid_markup_shapes(bot, style):
    spec = ScreenSpec(
        "Screen",
        inline_keyboard=inline() if style in {"inline", "hybrid"} else None,
        reply_keyboard=reply() if style in {"reply", "hybrid"} else None,
        reply_keyboard_key="main" if style in {"reply", "hybrid"} else None,
    )
    result = await render_spec(bot, spec)
    assert bot.send_message.await_count == (2 if style == "hybrid" else 1)
    assert result.view_id == "new"
    assert bot.edit_message_text.await_count == 0
    markup = bot.send_message.call_args_list[0].kwargs["reply_markup"]
    if style == "reply":
        assert isinstance(markup, ReplyKeyboardMarkup)
    elif style in {"inline", "hybrid"}:
        assert isinstance(markup, InlineKeyboardMarkup)
    else:
        assert markup is None
    if style == "hybrid":
        assert isinstance(
            bot.send_message.call_args_list[1].kwargs["reply_markup"], ReplyKeyboardMarkup
        )
        assert result.messages[-1].role == "tray"


async def test_inline_refresh_keeps_semantically_unchanged_tray(bot):
    previous = ViewState("old", (MessageRef(42, 2), MessageRef(42, 3, "tray")), "main", "en", "en")
    spec = ScreenSpec(
        "Tab", inline_keyboard=inline(), reply_keyboard=reply(), reply_keyboard_key="main"
    )
    result = await render_spec(bot, spec, request(bot, previous=previous))
    assert bot.edit_message_text.await_count == 1
    assert bot.send_message.await_count == 0
    assert result.messages == previous.messages
    assert result.reply_keyboard_locale == "en"


async def test_omitting_reply_markup_preserves_actual_installed_locale(bot):
    previous = ViewState("old", (MessageRef(42, 2),), "main", "en", "en")
    result = await render_spec(
        bot,
        ScreenSpec("Nouvel écran", inline_keyboard=inline()),
        request(bot, previous=previous, locale="fr"),
    )
    assert result.locale == "fr" and result.reply_keyboard_locale == "en"
    assert result.reply_keyboard_key == "main"
    assert bot.send_message.await_count == 0


async def test_locale_change_replaces_same_semantic_tray(bot):
    previous = ViewState("old", (MessageRef(42, 2),), "main", "en", "en")
    result = await render_spec(
        bot,
        ScreenSpec(
            "French", inline_keyboard=inline(), reply_keyboard=reply(), reply_keyboard_key="main"
        ),
        request(bot, previous=previous, locale="fr"),
    )
    assert bot.edit_message_text.await_count == 1
    assert bot.send_message.await_count == 1
    assert result.reply_keyboard_locale == "fr"


async def test_explicit_removal_uses_a_new_message(bot):
    previous = ViewState("old", (MessageRef(42, 2),), "cancel", "en", "en")
    result = await render_spec(
        bot,
        ScreenSpec("Done", inline_keyboard=inline(), reply_keyboard=ReplyKeyboardRemove()),
        request(bot, previous=previous),
    )
    assert isinstance(bot.send_message.call_args.kwargs["reply_markup"], ReplyKeyboardRemove)
    assert result.reply_keyboard_key is None and result.reply_keyboard_locale is None


async def test_partial_hybrid_replays_confirmed_content_without_resending(bot):
    ledger = Ledger()
    req = request(bot, ledger=ledger)
    spec = ScreenSpec(
        "Screen", inline_keyboard=inline(), reply_keyboard=reply(), reply_keyboard_key="main"
    )
    original = bot.send_message.side_effect
    calls = 0

    async def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=42, text="tray"), message="rate", retry_after=1
            )
        return await original(*args, **kwargs)

    bot.send_message.side_effect = flaky
    with pytest.raises(TelegramRetryAfter):
        await render_spec(bot, spec, req)
    result = await render_spec(bot, spec, req)
    assert bot.send_message.await_count == 3
    assert len(result.messages) == 2


async def test_unknown_send_is_never_automatically_repeated(bot):
    ledger = Ledger()
    req = request(bot, ledger=ledger)
    bot.send_message.side_effect = TimeoutError("response lost")
    with pytest.raises(TimeoutError):
        await render_spec(bot, ScreenSpec("Screen"), req)
    with pytest.raises(RenderUnknown):
        await render_spec(bot, ScreenSpec("Changed"), req)
    assert bot.send_message.await_count == 1
    assert ledger.results["text.plan"]["text"] == "Screen"


async def test_definitely_uneditable_content_can_fall_back_to_send(bot):
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=EditMessageText(text="screen", chat_id=42, message_id=2),
        message="message to edit not found",
    )
    previous = ViewState("old", (MessageRef(42, 2),))
    result = await render_spec(bot, ScreenSpec("Screen"), request(bot, previous=previous))
    assert result.messages[0].message_id != 2 and bot.send_message.await_count == 1


async def test_not_modified_edit_is_a_confirmed_idempotent_effect(bot):
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=EditMessageText(text="screen", chat_id=42, message_id=2),
        message="message is not modified",
    )
    result = await render_spec(
        bot, ScreenSpec("Screen"), request(bot, previous=ViewState("old", (MessageRef(42, 2),)))
    )
    assert result.messages == (MessageRef(42, 2),)
    assert bot.send_message.await_count == 0


async def test_explicit_edit_never_silently_sends(bot):
    with pytest.raises(ConfigurationError):
        await render_spec(bot, ScreenSpec("Screen", delivery="edit"))
    assert bot.send_message.await_count == 0
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=EditMessageText(text="screen", chat_id=42, message_id=2),
        message="message can't be edited",
    )
    with pytest.raises(RenderFailed):
        await render_spec(
            bot,
            ScreenSpec("Screen", delivery="edit"),
            request(bot, previous=ViewState("old", (MessageRef(42, 2),))),
        )
    assert bot.send_message.await_count == 0


async def test_cleanup_skips_current_message_and_all_trays(bot):
    presenter = TextPresenter({}, bot)
    old = ViewState("old", (MessageRef(42, 1), MessageRef(42, 2), MessageRef(42, 3, "tray")))
    current = ViewState("new", (MessageRef(42, 2),))
    cleaned = await presenter.cleanup(CleanupRequest(KEY, old, current))
    assert cleaned.messages == (MessageRef(42, 1),)
    assert bot.edit_message_reply_markup.await_count == 1
    assert bot.send_message.await_count == 0


async def test_no_prepared_effect_recorder_means_no_send(bot):
    with pytest.raises(ConfigurationError):
        await render_spec(bot, ScreenSpec("Screen"), replace(request(bot), effects=None))
    assert bot.send_message.await_count == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"text": ""},
        {"text": "x" * 4097},
        {"text": "ok", "reply_keyboard": reply()},
        {"text": "ok", "reply_keyboard_key": "orphan"},
        {"text": "ok", "delivery": "unknown"},
    ],
)
def test_invalid_screen_plans_are_rejected(kwargs):
    with pytest.raises(ConfigurationError):
        ScreenSpec(**kwargs)


async def test_unknown_edit_response_does_not_trigger_fallback_send(bot):
    bot.edit_message_text.side_effect = TimeoutError("edit outcome uncertain")
    with pytest.raises(TimeoutError):
        await render_spec(
            bot, ScreenSpec("Screen"), request(bot, previous=ViewState("old", (MessageRef(42, 2),)))
        )
    assert bot.send_message.await_count == 0


async def test_strict_edit_can_deliver_reply_tray_separately(bot):
    previous = ViewState("old", (MessageRef(42, 2),))
    result = await render_spec(
        bot,
        ScreenSpec("Screen", reply_keyboard=reply(), reply_keyboard_key="main", delivery="edit"),
        request(bot, previous=previous),
    )
    assert bot.edit_message_text.await_count == 1
    assert bot.send_message.await_count == 1
    assert isinstance(bot.send_message.call_args.kwargs["reply_markup"], ReplyKeyboardMarkup)
    assert result.messages[-1].role == "tray"


async def test_obsolete_message_cleanup_failure_is_observational(bot):
    bot.edit_message_reply_markup.side_effect = TelegramBadRequest(
        method=EditMessageText(text="screen", chat_id=42, message_id=2),
        message="message to edit not found",
    )
    result = await TextPresenter({}, bot).cleanup(
        CleanupRequest(KEY, ViewState("old", (MessageRef(42, 2),)), None)
    )
    assert result.unavailable and result.messages == ()
    assert bot.send_message.await_count == 0


async def test_no_previous_cleanup_is_empty(bot):
    assert (await TextPresenter({}, bot).cleanup(CleanupRequest(KEY, None, None))).messages == ()
    assert bot.edit_message_reply_markup.await_count == 0


async def test_recorded_plan_is_revalidated_before_any_effect(bot):
    ledger = Ledger()
    ledger.results["text.plan"] = {"text": "incomplete plan"}
    with pytest.raises(ConfigurationError):
        await render_spec(bot, ScreenSpec("Screen"), request(bot, ledger=ledger))
    assert bot.send_message.await_count == 0


async def test_missing_renderer_and_wrong_bot_are_setup_errors(bot):
    with pytest.raises(ConfigurationError):
        await TextPresenter({}, bot).render(request(bot))
    different = Bot("2:ABC")
    try:
        with pytest.raises(ConfigurationError):
            await render_spec(bot, ScreenSpec("Screen"), replace(request(bot), bot=different))
    finally:
        await different.session.close()
    assert bot.send_message.await_count == 0


def test_keyboard_inputs_are_defensively_copied():
    original = reply()
    spec = ScreenSpec("Screen", reply_keyboard=original, reply_keyboard_key="main")
    original.keyboard[0][0].text = "Mutated"
    assert spec.reply_keyboard.keyboard[0][0].text == "Home"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"text": 123},
        {"text": "Screen", "tray_text": ""},
        {"text": "Screen", "silent": "yes"},
        {"text": "Screen", "parse_mode": "custom"},
        {"text": "Screen", "inline_keyboard": {}},
        {"text": "Screen", "reply_keyboard": {}},
    ],
)
def test_invalid_scalar_and_markup_types_fail_before_delivery(kwargs):
    with pytest.raises(ConfigurationError):
        ScreenSpec(**kwargs)


async def test_partial_render_recovery_preserves_recorded_display_locale(bot):
    ledger = Ledger()
    req = request(bot, ledger=ledger, locale="en")
    spec = ScreenSpec(
        "English screen",
        inline_keyboard=inline(),
        reply_keyboard=reply(),
        reply_keyboard_key="main",
    )
    original = bot.send_message.side_effect
    calls = 0

    async def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=42, text="tray"), message="rate", retry_after=1
            )
        return await original(*args, **kwargs)

    bot.send_message.side_effect = flaky
    with pytest.raises(TelegramRetryAfter):
        await render_spec(bot, spec, req)
    recovered = await render_spec(
        bot,
        ScreenSpec("French replacement", reply_keyboard=reply(), reply_keyboard_key="main"),
        replace(req, locale="fr"),
    )
    assert bot.send_message.await_count == 3
    assert recovered.locale == "en"
    assert recovered.reply_keyboard_locale == "en"
    assert ledger.results["text.plan"]["locale"] == "en"
    assert ledger.results["text.plan"]["text"] == "English screen"
    assert bot.send_message.call_args.kwargs["reply_markup"].keyboard[0][0].text == "Home"
