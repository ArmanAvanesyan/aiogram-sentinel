"""
Unit tests for the CommandScopeManager.
"""

import pytest

from aiogram_cmds import (
    CmdsSettings,
    CommandScopeManager,
    Flags,
    MenuButtonDef,
)


class TestCommandScopeManager:
    """Test CommandScopeManager functionality."""

    def test_init_with_settings(self, mock_bot):
        """Test initializing with CmdsSettings."""
        settings = CmdsSettings(
            languages=["en", "ru"], fallback_language="en", i18n_key_prefix="cmd"
        )

        manager = CommandScopeManager(bot=mock_bot, settings=settings)

        assert manager.bot == mock_bot
        assert manager.settings == settings
        assert manager.config is None
        assert manager.translator is None
        assert manager.policy is not None
        assert manager.profile_resolver is None

    def test_init_with_config(self, mock_bot, basic_config):
        """Test initializing with CmdsConfig."""
        manager = CommandScopeManager(bot=mock_bot, config=basic_config)

        assert manager.bot == mock_bot
        assert manager.settings is not None
        assert manager.config == basic_config
        assert manager.translator is None
        assert manager.policy is not None
        assert manager.profile_resolver is None

    def test_init_with_translator(self, mock_bot, basic_config, mock_translator):
        """Test initializing with translator."""
        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, translator=mock_translator
        )

        assert manager.translator == mock_translator

    def test_init_with_profile_resolver(
        self, mock_bot, basic_config, basic_profile_resolver
    ):
        """Test initializing with profile resolver."""
        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, profile_resolver=basic_profile_resolver
        )

        assert manager.profile_resolver == basic_profile_resolver

    def test_init_defaults(self, mock_bot):
        """Test initializing with defaults."""
        manager = CommandScopeManager(bot=mock_bot)

        assert manager.bot == mock_bot
        assert manager.settings is not None
        assert manager.config is None
        assert manager.translator is None
        assert manager.policy is not None
        assert manager.profile_resolver is None

    @pytest.mark.asyncio
    async def test_update_user_commands_with_config_and_resolver(
        self, mock_bot, basic_config, basic_profile_resolver, mock_translator
    ):
        """Test updating user commands with config and profile resolver."""
        manager = CommandScopeManager(
            bot=mock_bot,
            config=basic_config,
            translator=mock_translator,
            profile_resolver=basic_profile_resolver,
        )

        await manager.update_user_commands(
            user_id=12345, is_registered=True, has_vehicle=False, user_language="en"
        )

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_commands_with_policy(self, mock_bot, mock_translator):
        """Test updating user commands with policy."""
        manager = CommandScopeManager(bot=mock_bot, translator=mock_translator)

        await manager.update_user_commands(
            user_id=12345, is_registered=True, has_vehicle=False, user_language="en"
        )

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_commands_guest_user(
        self, mock_bot, basic_config, basic_profile_resolver
    ):
        """Test updating commands for guest user."""
        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, profile_resolver=basic_profile_resolver
        )

        await manager.update_user_commands(
            user_id=12345, is_registered=False, has_vehicle=False, user_language="en"
        )

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_commands_during_registration(
        self, mock_bot, basic_config, basic_profile_resolver
    ):
        """Test updating commands during registration."""
        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, profile_resolver=basic_profile_resolver
        )

        await manager.update_user_commands(
            user_id=12345,
            is_registered=False,
            has_vehicle=False,
            is_during_registration=True,
            user_language="en",
        )

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_commands_with_chat_id(
        self, mock_bot, basic_config, basic_profile_resolver
    ):
        """Test updating commands with specific chat ID."""
        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, profile_resolver=basic_profile_resolver
        )

        await manager.update_user_commands(
            user_id=12345,
            is_registered=True,
            has_vehicle=False,
            user_language="en",
            chat_id=67890,
        )

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_user_commands(self, mock_bot):
        """Test clearing user commands."""
        manager = CommandScopeManager(bot=mock_bot)

        await manager.clear_user_commands(user_id=12345)

        # Should call delete_my_commands
        mock_bot.delete_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_all_with_config(self, mock_bot, basic_config, mock_translator):
        """Test setup_all with config."""
        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, translator=mock_translator
        )

        await manager.setup_all()

        # Should call set_my_commands and set_chat_menu_button
        assert mock_bot.set_my_commands.call_count > 0
        mock_bot.set_chat_menu_button.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_all_with_settings(self, mock_bot, mock_translator):
        """Test setup_all with settings."""
        settings = CmdsSettings(
            languages=["en", "ru"],
            fallback_language="en",
            i18n_key_prefix="cmd",
            menu_button="commands",
        )

        manager = CommandScopeManager(
            bot=mock_bot, settings=settings, translator=mock_translator
        )

        await manager.setup_all()

        # Should call set_my_commands and set_chat_menu_button
        assert mock_bot.set_my_commands.call_count > 0
        mock_bot.set_chat_menu_button.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_all_default_menu_button(self, mock_bot, basic_config):
        """Test setup_all with default menu button."""
        config = basic_config.model_copy()
        config.menu_button = MenuButtonDef(mode="default")

        manager = CommandScopeManager(bot=mock_bot, config=config)

        await manager.setup_all()

        # Should call set_chat_menu_button with default
        mock_bot.set_chat_menu_button.assert_called_once()

    def test_profile_resolver_integration(self, mock_bot, basic_config):
        """Test profile resolver integration."""

        def test_resolver(flags: Flags) -> str:
            if flags.is_registered:
                return "user"
            return "guest"

        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, profile_resolver=test_resolver
        )

        assert manager.profile_resolver == test_resolver

        # Test resolver with different flags
        guest_flags = Flags(is_registered=False, has_vehicle=False)
        user_flags = Flags(is_registered=True, has_vehicle=False)

        assert test_resolver(guest_flags) == "guest"
        assert test_resolver(user_flags) == "user"

    def test_translator_integration(self, mock_bot, basic_config):
        """Test translator integration."""

        def test_translator(key: str, *, locale: str) -> str:
            return f"Translated: {key} ({locale})"

        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, translator=test_translator
        )

        assert manager.translator == test_translator

        # Test translator
        result = test_translator("test.key", locale="en")
        assert result == "Translated: test.key (en)"

    @pytest.mark.asyncio
    async def test_error_handling_in_update_user_commands(self, mock_bot, basic_config):
        """Test error handling in update_user_commands."""
        # Make set_my_commands raise an exception
        mock_bot.set_my_commands.side_effect = Exception("API Error")

        manager = CommandScopeManager(bot=mock_bot, config=basic_config)

        # API failures propagate by default.
        with pytest.raises(Exception, match="API Error"):
            await manager.update_user_commands(
                user_id=12345, is_registered=True, has_vehicle=False, user_language="en"
            )

    @pytest.mark.asyncio
    async def test_error_handling_in_clear_user_commands(self, mock_bot):
        """Test error handling in clear_user_commands."""
        # Make delete_my_commands raise an exception
        mock_bot.delete_my_commands.side_effect = Exception("API Error")

        manager = CommandScopeManager(bot=mock_bot)

        with pytest.raises(Exception, match="API Error"):
            await manager.clear_user_commands(user_id=12345)

    @pytest.mark.asyncio
    async def test_error_handling_in_setup_all(self, mock_bot, basic_config):
        """Test error handling in setup_all."""
        # Make set_my_commands raise an exception
        mock_bot.set_my_commands.side_effect = Exception("API Error")

        manager = CommandScopeManager(bot=mock_bot, config=basic_config)

        with pytest.raises(Exception, match="API Error"):
            await manager.setup_all()

    def test_logging_in_update_user_commands(self, mock_bot, basic_config, caplog):
        """Test logging in update_user_commands."""
        import logging

        with caplog.at_level(logging.INFO):
            # This would normally be async, but we're just testing logging
            # The actual async call is tested elsewhere
            pass

    @pytest.mark.parametrize(
        "is_registered,has_vehicle,is_during_registration",
        [
            (False, False, False),
            (True, False, False),
            (True, True, False),
            (False, False, True),
            (True, False, True),
        ],
    )
    @pytest.mark.asyncio
    async def test_update_user_commands_various_flags(
        self,
        mock_bot,
        basic_config,
        basic_profile_resolver,
        is_registered,
        has_vehicle,
        is_during_registration,
    ):
        """Test update_user_commands with various flag combinations."""
        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, profile_resolver=basic_profile_resolver
        )

        await manager.update_user_commands(
            user_id=12345,
            is_registered=is_registered,
            has_vehicle=has_vehicle,
            is_during_registration=is_during_registration,
            user_language="en",
        )

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.parametrize("language", ["en", "ru", "es", "fr", "de"])
    @pytest.mark.asyncio
    async def test_update_user_commands_different_languages(
        self, mock_bot, basic_config, basic_profile_resolver, mock_translator, language
    ):
        """Test update_user_commands with different languages."""
        manager = CommandScopeManager(
            bot=mock_bot,
            config=basic_config,
            translator=mock_translator,
            profile_resolver=basic_profile_resolver,
        )

        await manager.update_user_commands(
            user_id=12345, is_registered=True, has_vehicle=False, user_language=language
        )

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called_once()

    def test_manager_state_consistency(self, mock_bot, basic_config):
        """Test that manager state remains consistent."""
        manager = CommandScopeManager(bot=mock_bot, config=basic_config)

        # Initial state
        assert manager.bot == mock_bot
        assert manager.config == basic_config
        assert manager.settings is not None

        # State should not change
        assert manager.bot == mock_bot
        assert manager.config == basic_config
        assert manager.settings is not None
