"""
Pytest configuration and shared fixtures for aiogram-cmds tests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, User

from aiogram_cmds import (
    CmdsConfig,
    CommandDef,
    CommandScopeManager,
    Flags,
    MenuButtonDef,
    ProfileDef,
    ScopeDef,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_bot():
    """Create a mock Bot instance."""
    bot = AsyncMock(spec=Bot)
    bot.token = "test_token"
    bot.get_me = AsyncMock(
        return_value=User(
            id=123456789, is_bot=True, first_name="Test Bot", username="testbot"
        )
    )
    bot.set_my_commands = AsyncMock(return_value=True)
    bot.delete_my_commands = AsyncMock(return_value=True)
    bot.set_chat_menu_button = AsyncMock(return_value=True)
    return bot


@pytest.fixture
def mock_user():
    """Create a mock User instance."""
    return User(
        id=123456789,
        is_bot=False,
        first_name="Test",
        last_name="User",
        username="testuser",
        language_code="en",
    )


@pytest.fixture
def mock_chat():
    """Create a mock Chat instance."""
    return Chat(id=123456789, type="private")


@pytest.fixture
def mock_message(mock_user, mock_chat):
    """Create a mock Message instance."""
    return Message(
        message_id=1,
        date=1234567890,
        chat=mock_chat,
        from_user=mock_user,
        text="/start",
    )


@pytest.fixture
def basic_config():
    """Create a basic CmdsConfig for testing."""
    return CmdsConfig(
        languages=["en", "ru"],
        fallback_language="en",
        i18n_key_prefix="cmd",
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "profile": CommandDef(i18n_key="profile.desc"),
        },
        profiles={
            "guest": ProfileDef(include=["start", "help"]),
            "user": ProfileDef(include=["start", "help", "profile"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
        ],
        menu_button=MenuButtonDef(mode="commands"),
    )


@pytest.fixture
def advanced_config():
    """Create an advanced CmdsConfig for testing."""
    return CmdsConfig(
        languages=["en", "ru", "es"],
        fallback_language="en",
        i18n_key_prefix="cmd",
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "profile": CommandDef(i18n_key="profile.desc"),
            "admin": CommandDef(i18n_key="admin.desc"),
            "ban": CommandDef(i18n_key="ban.desc"),
        },
        profiles={
            "guest": ProfileDef(include=["start", "help"]),
            "user": ProfileDef(include=["start", "help", "profile"]),
            "admin": ProfileDef(include=["start", "help", "profile", "admin", "ban"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
            ScopeDef(scope="chat", chat_id=12345, profile="admin"),
        ],
        menu_button=MenuButtonDef(mode="commands"),
    )


@pytest.fixture
def mock_translator():
    """Create a mock Translator."""

    def translator(key: str, *, locale: str) -> str:
        translations = {
            "en": {
                "cmd.start.desc": "Start the bot",
                "cmd.help.desc": "Show help information",
                "cmd.profile.desc": "View your profile",
                "cmd.admin.desc": "Admin panel",
                "cmd.ban.desc": "Ban user",
            },
            "ru": {
                "cmd.start.desc": "Запустить бота",
                "cmd.help.desc": "Показать справку",
                "cmd.profile.desc": "Посмотреть профиль",
                "cmd.admin.desc": "Панель администратора",
                "cmd.ban.desc": "Заблокировать пользователя",
            },
            "es": {
                "cmd.start.desc": "Iniciar el bot",
                "cmd.help.desc": "Mostrar ayuda",
                "cmd.profile.desc": "Ver tu perfil",
                "cmd.admin.desc": "Panel de administración",
                "cmd.ban.desc": "Banear usuario",
            },
        }
        return translations.get(locale, {}).get(key) or key

    return translator


@pytest.fixture
def noop_translator():
    """Create a no-op translator that returns None."""

    def translator(key: str, *, locale: str) -> str | None:
        return None

    return translator


@pytest.fixture
def basic_profile_resolver():
    """Create a basic profile resolver for testing."""

    def resolver(flags: Flags) -> str:
        if flags.is_registered:
            return "user"
        return "guest"

    return resolver


@pytest.fixture
def advanced_profile_resolver():
    """Create an advanced profile resolver for testing."""

    def resolver(flags: Flags) -> str:
        if hasattr(flags, "is_admin") and flags.is_admin:
            return "admin"
        elif flags.is_registered:
            return "user"
        return "guest"

    return resolver


@pytest.fixture
def command_manager(mock_bot, basic_config, mock_translator, basic_profile_resolver):
    """Create a CommandScopeManager instance for testing."""
    return CommandScopeManager(
        bot=mock_bot,
        config=basic_config,
        translator=mock_translator,
        profile_resolver=basic_profile_resolver,
    )


@pytest.fixture
def sample_flags():
    """Create sample Flags instances for testing."""
    return {
        "guest": Flags(is_registered=False, has_vehicle=False),
        "user": Flags(is_registered=True, has_vehicle=False),
        "premium": Flags(is_registered=True, has_vehicle=True),
        "during_registration": Flags(
            is_registered=False, has_vehicle=False, is_during_registration=True
        ),
    }


@pytest.fixture
def sample_command_names():
    """Create sample command names for testing."""
    return [
        "start",
        "help",
        "profile",
        "settings",
        "admin",
        "ban",
        "unban",
    ]


@pytest.fixture
def sample_bot_commands():
    """Create sample BotCommand instances for testing."""
    from aiogram.types import BotCommand

    return [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Show help information"),
        BotCommand(command="profile", description="View your profile"),
    ]


@pytest.fixture
def mock_i18n():
    """Create a mock i18n instance."""
    i18n = MagicMock()
    i18n.gettext = MagicMock(
        side_effect=lambda key, locale="en": {
            "cmd.start.desc": "Start the bot",
            "cmd.help.desc": "Show help information",
            "cmd.profile.desc": "View your profile",
        }.get(key, key)
    )
    return i18n


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary configuration file."""
    config_content = """
[tool.aiogram_cmds]
languages = ["en", "ru", "es"]
fallback_language = "en"
i18n_key_prefix = "cmd"
profile = "default"
menu_button = "commands"
"""

    config_file = tmp_path / "pyproject.toml"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def temp_translation_files(tmp_path):
    """Create temporary translation files."""
    locales_dir = tmp_path / "locales"

    # English
    en_dir = locales_dir / "en" / "LC_MESSAGES"
    en_dir.mkdir(parents=True)
    en_file = en_dir / "messages.po"
    en_file.write_text("""
msgid "cmd.start.desc"
msgstr "Start the bot"

msgid "cmd.help.desc"
msgstr "Show help information"
""")

    # Russian
    ru_dir = locales_dir / "ru" / "LC_MESSAGES"
    ru_dir.mkdir(parents=True)
    ru_file = ru_dir / "messages.po"
    ru_file.write_text("""
msgid "cmd.start.desc"
msgstr "Запустить бота"

msgid "cmd.help.desc"
msgstr "Показать справку"
""")

    return locales_dir


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.set = AsyncMock()
    redis_client.setex = AsyncMock()
    redis_client.delete = AsyncMock()
    redis_client.hget = AsyncMock(return_value=None)
    redis_client.hset = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)
    return redis_client


@pytest.fixture
def mock_database():
    """Create a mock database connection."""
    db = AsyncMock()
    db.fetchrow = AsyncMock(
        return_value={
            "id": 123456789,
            "registered": True,
            "premium": False,
            "admin": False,
            "banned": False,
        }
    )
    db.fetch = AsyncMock(return_value=[])
    db.execute = AsyncMock()
    return db


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "perf: mark test as a performance test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_collection_modifyitems(config, items):
    """Modify test collection."""
    # Mark tests based on their location
    for item in items:
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "perf" in str(item.fspath):
            item.add_marker(pytest.mark.perf)

        # Mark slow tests
        if "slow" in item.name or "benchmark" in item.name:
            item.add_marker(pytest.mark.slow)
