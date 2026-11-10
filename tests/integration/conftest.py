"""
Shared fixtures for integration tests.
"""

from unittest.mock import AsyncMock

import pytest
from aiogram import Bot


@pytest.fixture
async def mock_bot():
    """Create a mock Bot instance for testing."""
    bot = AsyncMock(spec=Bot)

    # Configure mock methods
    bot.set_my_commands = AsyncMock(return_value=True)
    bot.delete_my_commands = AsyncMock(return_value=True)
    bot.set_chat_menu_button = AsyncMock(return_value=True)

    return bot


@pytest.fixture
def mock_i18n():
    """Create a mock i18n instance for testing."""
    mock_i18n = AsyncMock()

    def mock_gettext(key, locale=None):
        # Simple mock translation
        translations = {
            "start.desc": "Start",
            "help.desc": "Help",
            "profile.desc": "Profile",
            "admin.desc": "Admin",
            "settings.desc": "Settings",
        }
        return translations.get(key, key)

    mock_i18n.gettext = mock_gettext
    return mock_i18n


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    from aiogram_cmds.customize import (
        CmdsConfig,
        CommandDef,
        MenuButtonDef,
        ProfileDef,
        ScopeDef,
    )

    return CmdsConfig(
        languages=["en", "ru"],
        fallback_language="en",
        i18n_key_prefix="bot",
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "profile": CommandDef(i18n_key="profile.desc"),
            "admin": CommandDef(i18n_key="admin.desc"),
        },
        profiles={
            "guest": ProfileDef(include=["start", "help"]),
            "user": ProfileDef(include=["start", "help", "profile"]),
            "admin": ProfileDef(include=["start", "help", "profile", "admin"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
        ],
        menu_button=MenuButtonDef(mode="commands"),
    )


@pytest.fixture
def sample_settings():
    """Create sample settings for testing."""
    from aiogram_cmds.settings import CmdsSettings

    return CmdsSettings(
        languages=["en", "ru"],
        fallback_language="en",
        i18n_key_prefix="bot",
        profile="default",
        menu_button="commands",
    )
