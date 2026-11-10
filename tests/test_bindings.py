"""Native command parsing, semantic localization and prepared opaque controls."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.types import Chat, Message, User

from aiogram_nav.errors import ConfigurationError, InvalidParameters, NodeNotFound
from aiogram_nav.inputs import (
    CallbackEntry,
    CommandEntry,
    InputBindings,
    ReplyEntry,
    parse_callback_data,
    prepare_token,
)
from aiogram_nav.models import ConversationKey, NavigationAction, Node
from aiogram_nav.registry import NavigationRegistry


@pytest_asyncio.fixture
async def bot():
    value = Bot("1:ABC")
    value.me = AsyncMock(
        return_value=User(id=1, is_bot=True, first_name="Demo", username="DemoBot")
    )
    yield value
    await value.session.close()


def message(text):
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=42, type="private"),
        from_user=User(id=42, is_bot=False, first_name="User"),
        text=text,
    )


def registry():
    return NavigationRegistry(
        roots={"main"},
        nodes=[
            Node("main", renderer="main"),
            Node("settings", parent="main", renderer="settings"),
            Node("group", parent="main"),
        ],
    )


async def test_native_command_parser_handles_mentions_and_decoded_arguments(bot):
    seen = []

    def decode(command):
        seen.append(command)
        return {"page": int(command.args)}

    bindings = InputBindings([CommandEntry("open", "open", "settings", decoder=decode)])
    result = await bindings.match_command(message("/open@DemoBot 17"), bot, "main")
    assert result.params == {"page": 17}
    assert result.action == NavigationAction("go", "settings", {"page": 17})
    assert seen[0].mention == "DemoBot"
    assert await bindings.match_command(message("/open@OtherBot 17"), bot, "main") is None
    assert await bindings.match_command(message("ordinary /open 17"), bot, "main") is None
    with pytest.raises(InvalidParameters):
        await bindings.match_command(message("/open invalid"), bot, "main")


async def test_command_scopes_globals_and_async_decoders(bot):
    async def decode(command):
        return {"argument": command.args}

    bindings = InputBindings(
        [
            CommandEntry("home", "home", action="home", global_action=True),
            CommandEntry("settings", "settings", "settings", frozenset({"main"}), decoder=decode),
        ]
    )
    assert (
        await bindings.match_command(message("/home"), bot, "typing", global_only=True)
    ).entry.id == "home"
    assert await bindings.match_command(message("/home"), bot, "typing", global_only=False) is None
    assert await bindings.match_command(message("/settings"), bot, "typing") is None
    found = await bindings.match_command(message("/settings extra"), bot, "main", global_only=False)
    assert found.params == {"argument": "extra"}


async def test_argumentless_bindings_reject_unhandled_arguments(bot):
    bindings = InputBindings([CommandEntry("settings", "settings", "settings")])
    with pytest.raises(InvalidParameters):
        await bindings.match_command(message("/settings silently-dropped"), bot, "main")


@pytest.mark.parametrize(
    "entries",
    [
        [CommandEntry("same", "a", "main"), ReplyEntry("same", "label", "main")],
        [CommandEntry("one", "a", "main"), CommandEntry("two", "a", "main")],
        [CallbackEntry("one", "open", "main"), CallbackEntry("two", "open", "main")],
    ],
)
def test_ambiguous_or_duplicate_declarations_are_rejected(entries):
    with pytest.raises(ConfigurationError):
        InputBindings(entries)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CommandEntry("invalid", "/bad", "main"),
        lambda: ReplyEntry("missing-target", "label"),
        lambda: ReplyEntry("invalid-action", "label", "main", action="back"),
        lambda: CallbackEntry("missing-target", "open"),
    ],
)
def test_invalid_entry_shapes_are_rejected(factory):
    with pytest.raises(ConfigurationError):
        factory()


def test_scope_disjoint_commands_and_reply_labels_are_valid():
    bindings = InputBindings(
        [
            CommandEntry("one", "open", "main", frozenset({"main"})),
            CommandEntry("two", "open", "settings", frozenset({"settings"})),
            ReplyEntry("reply-one", "label", "main", frozenset({"main"})),
            ReplyEntry("reply-two", "label", "settings", frozenset({"settings"})),
        ]
    )
    bindings.validate(registry())
    bindings.validate_labels(lambda key, locale: "Open", locales=["en", "fr"])
    assert (
        bindings.match_reply(
            "Open", "settings", current_locale="en", translator=lambda key, locale: "Open"
        ).entry.id
        == "reply-two"
    )


def test_reply_matches_only_current_and_installed_locale_and_exact_text():
    labels = {
        ("settings", "en"): "Settings",
        ("settings", "fr"): "Réglages",
        ("settings", "hy"): "Կարգավորումներ",
    }
    bindings = InputBindings([ReplyEntry("settings", "settings", "settings", frozenset({"main"}))])

    def translate(key, locale):
        return labels[key, locale]

    assert (
        bindings.match_reply(
            "Settings", "main", current_locale="fr", installed_locale="en", translator=translate
        ).entry.id
        == "settings"
    )
    assert (
        bindings.match_reply(
            "Réglages", "main", current_locale="fr", installed_locale="en", translator=translate
        ).entry.id
        == "settings"
    )
    assert (
        bindings.match_reply(
            "Կարգավորումներ",
            "main",
            current_locale="fr",
            installed_locale="en",
            translator=translate,
        )
        is None
    )
    assert (
        bindings.match_reply(
            "⚙ Settings", "main", current_locale="fr", installed_locale="en", translator=translate
        )
        is None
    )
    assert (
        bindings.match_reply("Settings", "typing", current_locale="en", translator=translate)
        is None
    )


def test_free_typing_can_disable_scoped_reply_navigation():
    bindings = InputBindings(
        [
            ReplyEntry("settings", "settings", "settings"),
            ReplyEntry("home", "home", action="home", global_action=True),
        ]
    )
    assert (
        bindings.match_reply(
            "settings",
            "typing",
            current_locale="en",
            translator=lambda key, locale: key,
            allow_scoped=False,
        )
        is None
    )
    assert (
        bindings.match_reply(
            "home",
            "typing",
            current_locale="en",
            translator=lambda key, locale: key,
            allow_scoped=False,
        ).entry.id
        == "home"
    )


def test_ambiguous_catalogs_and_cross_locale_runtime_labels_fail_closed():
    bindings = InputBindings(
        [ReplyEntry("one", "one", "main"), ReplyEntry("two", "two", "settings")]
    )
    with pytest.raises(ConfigurationError):
        bindings.validate_labels(lambda key, locale: "Duplicate", locales=["en"])
    translations = {("one", "en"): "A", ("two", "en"): "B", ("one", "fr"): "B", ("two", "fr"): "C"}
    with pytest.raises(ConfigurationError):
        bindings.match_reply(
            "B",
            "main",
            current_locale="fr",
            installed_locale="en",
            translator=lambda key, locale: translations[key, locale],
        )
    with pytest.raises(ConfigurationError):
        bindings.match_reply("x", "main", current_locale="en", translator=lambda key, locale: "")


def test_registry_validation_rejects_unknown_and_abstract_targets():
    with pytest.raises(NodeNotFound):
        InputBindings([CommandEntry("missing", "missing", "missing")]).validate(registry())
    with pytest.raises(ConfigurationError):
        InputBindings([CommandEntry("abstract", "group", "group")]).validate(registry())
    with pytest.raises(ConfigurationError):
        InputBindings([CommandEntry("not-root", "home", "settings", action="home")]).validate(
            registry()
        )
    with pytest.raises(ConfigurationError):
        InputBindings([]).entry("unknown")


async def test_prepared_tokens_return_the_original_reserved_candidate_on_retry():
    class Repository:
        def __init__(self):
            self.saved = None

        async def reserve_token(self, key, token, *, operation_id):
            if self.saved is None:
                self.saved = token
            return self.saved

    repo = Repository()
    key = ConversationKey("test", 1, 42, 42)
    args = dict(
        session_id="session",
        view_id="view",
        action=NavigationAction("go", "main"),
        expires_at=10000,
        operation_id="button",
        entry_id="main-inline",
    )
    first = await prepare_token(repo, key, **args)
    second = await prepare_token(repo, key, **args)
    assert first == second
    assert parse_callback_data(first) == repo.saved.token
    assert repo.saved.actor_id == key.user_id and repo.saved.entry_id == "main-inline"
    assert len(first.encode()) <= 64
    with pytest.raises(ConfigurationError):
        await prepare_token(repo, key, **args, token="not-opaque")


@pytest.mark.parametrize(
    "data", ["", "other:token", "nav:", "nav:emoji-🙂-invalid", "nav:" + "x" * 61, "nav:x:y"]
)
def test_malformed_or_foreign_callback_data_is_inert(data):
    assert parse_callback_data(data) is None
