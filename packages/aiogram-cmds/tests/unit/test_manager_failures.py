"""Manager failures are observable and do not produce false success messages."""

import asyncio
import logging

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SetMyCommands

from aiogram_cmds import CommandScopeManager


@pytest.mark.parametrize("operation", ["update", "clear", "setup", "profile"])
@pytest.mark.parametrize("best_effort", [False, True])
async def test_api_failure_has_explicit_outcome(
    mock_bot, basic_config, caplog, operation, best_effort
):
    error = TelegramBadRequest(
        method=SetMyCommands(commands=[]), message="scope rejected"
    )
    mock_bot.set_my_commands.side_effect = error
    mock_bot.delete_my_commands.side_effect = error
    manager = CommandScopeManager(
        mock_bot, config=basic_config, best_effort=best_effort
    )
    calls = {
        "update": lambda: manager.update_user_commands(42, True, False),
        "clear": lambda: manager.clear_user_commands(42),
        "setup": manager.setup_all,
        "profile": lambda: manager.update_profile(42, "user"),
    }
    with caplog.at_level(logging.INFO, logger="aiogram_cmds.manager"):
        if best_effort:
            assert await calls[operation]() is False
        else:
            with pytest.raises(TelegramBadRequest) as caught:
                await calls[operation]()
            assert caught.value is error
    assert not any(record.levelno == logging.INFO for record in caplog.records)


async def test_generic_profile_does_not_require_application_flags(
    mock_bot, basic_config
):
    manager = CommandScopeManager(mock_bot, config=basic_config)
    assert await manager.update_profile(42, "user") is True
    mock_bot.set_my_commands.assert_awaited_once()


async def test_generic_profile_requires_configuration(mock_bot):
    with pytest.raises(ValueError, match="CmdsConfig"):
        await CommandScopeManager(mock_bot).update_profile(42, "user")


async def test_best_effort_never_suppresses_cancellation(mock_bot):
    mock_bot.delete_my_commands.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await CommandScopeManager(mock_bot, best_effort=True).clear_user_commands(42)
