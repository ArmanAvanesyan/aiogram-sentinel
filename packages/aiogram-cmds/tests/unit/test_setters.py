"""
Unit tests for the setters module.
"""

from unittest.mock import Mock

import pytest
from aiogram.types import (
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    MenuButtonCommands,
    MenuButtonDefault,
)

from aiogram_cmds.policy import Flags
from aiogram_cmds.setters import (
    clear_user_commands,
    set_user_commands_by_flags,
    setup_all_command_scopes,
)


class TestSetUserCommandsByFlags:
    """Test set_user_commands_by_flags function."""

    @pytest.mark.asyncio
    async def test_set_user_commands_by_flags_basic(self, mock_bot):
        """Test basic user command setting."""
        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=True,
            has_vehicle=False,
            is_during_registration=False,
            user_language="en",
        )

        # Should call set_my_commands once
        mock_bot.set_my_commands.assert_called_once()
        call_args = mock_bot.set_my_commands.call_args

        # Check arguments - commands is passed as keyword argument
        assert "commands" in call_args[1]
        assert call_args[1]["scope"].chat_id == 12345
        assert call_args[1]["language_code"] == "en"
        assert isinstance(call_args[1]["scope"], BotCommandScopeChat)

    @pytest.mark.asyncio
    async def test_set_user_commands_by_flags_with_translator(self, mock_bot):
        """Test user command setting with translator."""
        mock_translator = Mock()
        mock_translator.return_value = "Translated command"

        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=True,
            has_vehicle=False,
            is_during_registration=False,
            user_language="ru",
            translator=mock_translator,
            key_prefix="bot",
        )

        mock_bot.set_my_commands.assert_called_once()
        # Translator should be used in build_bot_commands
        mock_translator.assert_called()

    @pytest.mark.asyncio
    async def test_set_user_commands_by_flags_custom_policy(self, mock_bot):
        """Test user command setting with custom policy."""

        def custom_policy(flags: Flags) -> list[str]:
            if flags.is_registered:
                return ["start", "profile", "settings"]
            else:
                return ["start", "help"]

        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=True,
            has_vehicle=True,
            is_during_registration=False,
            user_language="en",
            policy=custom_policy,
        )

        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_user_commands_by_flags_during_registration(self, mock_bot):
        """Test user command setting during registration."""
        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=False,
            has_vehicle=False,
            is_during_registration=True,
            user_language="en",
        )

        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_user_commands_by_flags_unregistered_user(self, mock_bot):
        """Test user command setting for unregistered user."""
        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=False,
            has_vehicle=False,
            is_during_registration=False,
            user_language="en",
        )

        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_user_commands_by_flags_registered_with_vehicle(self, mock_bot):
        """Test user command setting for registered user with vehicle."""
        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=True,
            has_vehicle=True,
            is_during_registration=False,
            user_language="en",
        )

        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_user_commands_by_flags_different_languages(self, mock_bot):
        """Test user command setting with different languages."""
        languages = ["en", "ru", "es", "fr"]

        for lang in languages:
            await set_user_commands_by_flags(
                mock_bot,
                user_id=12345,
                is_registered=True,
                has_vehicle=False,
                is_during_registration=False,
                user_language=lang,
            )

        # Should call set_my_commands for each language
        assert mock_bot.set_my_commands.call_count == len(languages)

    @pytest.mark.asyncio
    async def test_set_user_commands_by_flags_custom_key_prefix(self, mock_bot):
        """Test user command setting with custom key prefix."""
        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=True,
            has_vehicle=False,
            is_during_registration=False,
            user_language="en",
            key_prefix="custom",
        )

        mock_bot.set_my_commands.assert_called_once()


class TestClearUserCommands:
    """Test clear_user_commands function."""

    @pytest.mark.asyncio
    async def test_clear_user_commands_basic(self, mock_bot):
        """Test basic user command clearing."""
        await clear_user_commands(mock_bot, user_id=12345)

        # Should call delete_my_commands once
        mock_bot.delete_my_commands.assert_called_once()
        call_args = mock_bot.delete_my_commands.call_args

        # Check arguments
        assert call_args[1]["scope"].chat_id == 12345
        assert isinstance(call_args[1]["scope"], BotCommandScopeChat)

    @pytest.mark.asyncio
    async def test_clear_user_commands_different_users(self, mock_bot):
        """Test clearing commands for different users."""
        user_ids = [12345, 67890, 11111]

        for user_id in user_ids:
            await clear_user_commands(mock_bot, user_id=user_id)

        # Should call delete_my_commands for each user
        assert mock_bot.delete_my_commands.call_count == len(user_ids)

        # Check that each call used the correct user_id
        calls = mock_bot.delete_my_commands.call_args_list
        for i, user_id in enumerate(user_ids):
            assert calls[i][1]["scope"].chat_id == user_id


class TestSetupAllCommandScopes:
    """Test setup_all_command_scopes function."""

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_basic(self, mock_bot):
        """Test basic setup of all command scopes."""
        languages = ("en", "ru")

        await setup_all_command_scopes(
            mock_bot,
            languages=languages,
            translator=None,
            key_prefix="cmd",
            menu_button="commands",
        )

        # Should call set_my_commands for default scope + each language
        expected_calls = 1 + len(languages)  # 1 for default + 1 for each language
        assert mock_bot.set_my_commands.call_count == expected_calls

        # Should call set_chat_menu_button once
        mock_bot.set_chat_menu_button.assert_called_once_with(
            menu_button=MenuButtonCommands()
        )

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_with_translator(self, mock_bot):
        """Test setup with translator."""
        mock_translator = Mock()
        mock_translator.return_value = "Translated command"

        languages = ("en", "ru", "es")

        await setup_all_command_scopes(
            mock_bot,
            languages=languages,
            translator=mock_translator,
            key_prefix="bot",
            menu_button="commands",
        )

        # Should call set_my_commands for default + each language
        expected_calls = 1 + len(languages)
        assert mock_bot.set_my_commands.call_count == expected_calls

        # Translator should be used
        mock_translator.assert_called()

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_custom_commands(self, mock_bot):
        """Test setup with custom default commands."""
        languages = ("en",)
        custom_commands = ["start", "help", "profile", "settings"]

        await setup_all_command_scopes(
            mock_bot,
            languages=languages,
            default_commands=custom_commands,
        )

        # Should call set_my_commands for default + each language
        expected_calls = 1 + len(languages)
        assert mock_bot.set_my_commands.call_count == expected_calls

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_menu_button_commands(self, mock_bot):
        """Test setup with commands menu button."""
        await setup_all_command_scopes(
            mock_bot,
            languages=("en",),
            menu_button="commands",
        )

        mock_bot.set_chat_menu_button.assert_called_once_with(
            menu_button=MenuButtonCommands()
        )

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_menu_button_default(self, mock_bot):
        """Test setup with default menu button."""
        await setup_all_command_scopes(
            mock_bot,
            languages=("en",),
            menu_button="default",
        )

        mock_bot.set_chat_menu_button.assert_called_once_with(
            menu_button=MenuButtonDefault()
        )

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_single_language(self, mock_bot):
        """Test setup with single language."""
        languages = ("en",)

        await setup_all_command_scopes(
            mock_bot,
            languages=languages,
        )

        # Should call set_my_commands twice: once for default, once for the language
        assert mock_bot.set_my_commands.call_count == 2

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_multiple_languages(self, mock_bot):
        """Test setup with multiple languages."""
        languages = ("en", "ru", "es", "fr", "de")

        await setup_all_command_scopes(
            mock_bot,
            languages=languages,
        )

        # Should call set_my_commands for default + each language
        expected_calls = 1 + len(languages)
        assert mock_bot.set_my_commands.call_count == expected_calls

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_custom_key_prefix(self, mock_bot):
        """Test setup with custom key prefix."""
        await setup_all_command_scopes(
            mock_bot,
            languages=("en",),
            key_prefix="custom",
        )

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called()

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_scope_types(self, mock_bot):
        """Test that correct scope types are used."""
        await setup_all_command_scopes(
            mock_bot,
            languages=("en", "ru"),
        )

        calls = mock_bot.set_my_commands.call_args_list

        # First call should be for default scope (no language_code)
        first_call = calls[0]
        assert isinstance(first_call[1]["scope"], BotCommandScopeDefault)
        assert "language_code" not in first_call[1]

        # Subsequent calls should be for all private chats with language codes
        for call in calls[1:]:
            assert isinstance(call[1]["scope"], BotCommandScopeAllPrivateChats)
            assert "language_code" in call[1]

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_empty_languages(self, mock_bot):
        """Test setup with empty languages tuple raises error."""
        languages = ()

        # Empty languages tuple should raise IndexError when trying to access languages[0]
        with pytest.raises(IndexError):
            await setup_all_command_scopes(
                mock_bot,
                languages=languages,
            )

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_no_default_commands(self, mock_bot):
        """Test setup with no default commands (should use default)."""
        await setup_all_command_scopes(
            mock_bot,
            languages=("en",),
            default_commands=None,
        )

        # Should still work with default commands
        mock_bot.set_my_commands.assert_called()

    @pytest.mark.asyncio
    async def test_setup_all_command_scopes_empty_default_commands(self, mock_bot):
        """Test setup with empty default commands."""
        await setup_all_command_scopes(
            mock_bot,
            languages=("en",),
            default_commands=[],
        )

        # Should still call set_my_commands
        mock_bot.set_my_commands.assert_called()


class TestSettersIntegration:
    """Integration tests for setters functionality."""

    @pytest.mark.asyncio
    async def test_full_workflow_setup_then_user_commands(self, mock_bot):
        """Test complete workflow: setup all scopes, then set user commands."""
        # First setup all command scopes
        await setup_all_command_scopes(
            mock_bot,
            languages=("en", "ru"),
            menu_button="commands",
        )

        # Then set user-specific commands
        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=True,
            has_vehicle=False,
            is_during_registration=False,
            user_language="en",
        )

        # Should have called set_my_commands for setup + user commands
        setup_calls = 3  # 1 default + 2 languages
        user_calls = 1
        total_expected = setup_calls + user_calls

        assert mock_bot.set_my_commands.call_count == total_expected
        mock_bot.set_chat_menu_button.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_with_clear_user_commands(self, mock_bot):
        """Test workflow: setup, set user commands, then clear user commands."""
        # Setup
        await setup_all_command_scopes(mock_bot, languages=("en",))

        # Set user commands
        await set_user_commands_by_flags(
            mock_bot,
            user_id=12345,
            is_registered=True,
            has_vehicle=False,
            is_during_registration=False,
        )

        # Clear user commands
        await clear_user_commands(mock_bot, user_id=12345)

        # Should have called set_my_commands for setup + user, and delete_my_commands for clear
        # Setup calls: 1 default + 1 language = 2, plus 1 user call = 3 total
        assert (
            mock_bot.set_my_commands.call_count == 3
        )  # 1 default + 1 language + 1 user
        mock_bot.delete_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_users_workflow(self, mock_bot):
        """Test workflow with multiple users."""
        # Setup global commands
        await setup_all_command_scopes(mock_bot, languages=("en", "ru"))

        # Set commands for multiple users
        users = [
            (12345, True, False, False, "en"),
            (67890, True, True, False, "ru"),
            (11111, False, False, False, "en"),
        ]

        for user_id, is_registered, has_vehicle, is_during_registration, lang in users:
            await set_user_commands_by_flags(
                mock_bot,
                user_id=user_id,
                is_registered=is_registered,
                has_vehicle=has_vehicle,
                is_during_registration=is_during_registration,
                user_language=lang,
            )

        # Should have setup calls + user calls
        setup_calls = 3  # 1 default + 2 languages
        user_calls = len(users)
        total_expected = setup_calls + user_calls

        assert mock_bot.set_my_commands.call_count == total_expected

    @pytest.mark.asyncio
    async def test_error_handling_in_setters(self, mock_bot):
        """Test error handling in setters functions."""
        # Make bot methods raise exceptions
        mock_bot.set_my_commands.side_effect = Exception("API Error")
        mock_bot.delete_my_commands.side_effect = Exception("API Error")
        mock_bot.set_chat_menu_button.side_effect = Exception("API Error")

        # These should raise exceptions (not handled in setters)
        # The setters functions don't handle exceptions, so they propagate
        # whatever exception the underlying aiogram methods raise
        with pytest.raises(Exception):  # noqa: B017
            await set_user_commands_by_flags(
                mock_bot,
                user_id=12345,
                is_registered=True,
                has_vehicle=False,
                is_during_registration=False,
            )

        with pytest.raises(Exception):  # noqa: B017
            await clear_user_commands(mock_bot, user_id=12345)

        with pytest.raises(Exception):  # noqa: B017
            await setup_all_command_scopes(mock_bot, languages=("en",))
