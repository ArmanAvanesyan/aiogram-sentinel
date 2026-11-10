"""
Shared fixtures for performance tests.
"""

from unittest.mock import AsyncMock

import pytest
from aiogram import Bot


@pytest.fixture
async def mock_bot():
    """Create a mock Bot instance for performance testing."""
    bot = AsyncMock(spec=Bot)

    # Configure mock methods to be fast
    bot.set_my_commands = AsyncMock(return_value=True)
    bot.delete_my_commands = AsyncMock(return_value=True)
    bot.set_chat_menu_button = AsyncMock(return_value=True)

    return bot


@pytest.fixture
def large_config():
    """Create a large configuration for performance testing."""
    from aiogram_cmds.customize import CmdsConfig, CommandDef, ProfileDef, ScopeDef

    return CmdsConfig(
        languages=["en", "ru", "es", "fr", "de"],
        commands={f"cmd_{i}": CommandDef(i18n_key=f"cmd_{i}.desc") for i in range(100)},
        profiles={
            f"profile_{i}": ProfileDef(
                include=[f"cmd_{j}" for j in range(i * 10, (i + 1) * 10)],
                exclude=[f"cmd_{j}" for j in range(i * 10, i * 10 + 2)],
            )
            for i in range(10)
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="profile_0"),
            ScopeDef(scope="all_group_chats", profile="profile_1"),
            ScopeDef(scope="default", profile="profile_2"),
        ],
    )
