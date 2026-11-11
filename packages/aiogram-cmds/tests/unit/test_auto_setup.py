"""
Unit tests for the auto_setup module.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from aiogram_cmds.auto_setup import (
    _try_import_i18n,
    create_default_config,
    create_default_profile_resolver,
    setup_commands_auto,
)
from aiogram_cmds.customize import (
    CmdsConfig,
    CommandDef,
    MenuButtonDef,
    ProfileDef,
    ScopeDef,
)
from aiogram_cmds.manager import CommandScopeManager
from aiogram_cmds.policy import Flags


class TestSetupCommandsAuto:
    """Test setup_commands_auto function."""

    @pytest.mark.asyncio
    async def test_setup_commands_auto_minimal(self, mock_bot):
        """Test minimal setup with just bot."""
        manager = await setup_commands_auto(mock_bot)

        assert isinstance(manager, CommandScopeManager)
        assert manager.bot == mock_bot
        assert manager.config is not None
        assert manager.profile_resolver is not None

    @pytest.mark.asyncio
    async def test_setup_commands_auto_with_languages(self, mock_bot):
        """Test setup with custom languages."""
        languages = ["en", "ru", "es"]
        manager = await setup_commands_auto(mock_bot, languages=languages)

        assert manager.config.languages == languages
        assert manager.config.fallback_language == "en"

    @pytest.mark.asyncio
    async def test_setup_commands_auto_with_i18n_instance(self, mock_bot):
        """Test setup with i18n instance."""
        mock_i18n = Mock()
        mock_i18n.gettext.return_value = "Translated text"
        # Mock with_locale context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_context)
        mock_context.__exit__ = Mock(return_value=None)
        mock_i18n.with_locale.return_value = mock_context

        manager = await setup_commands_auto(mock_bot, i18n_instance=mock_i18n)

        assert manager.translator is not None
        # Test that translator works
        result = manager.translator("test.key", locale="en")
        assert result == "Translated text"

    @pytest.mark.asyncio
    async def test_setup_commands_auto_with_custom_config(self, mock_bot):
        """Test setup with custom config."""
        custom_config = CmdsConfig(
            languages=["en"],
            commands={"custom": CommandDef(i18n_key="custom.desc")},
            profiles={"custom_profile": ProfileDef(include=["custom"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="custom_profile")],
        )

        manager = await setup_commands_auto(mock_bot, config=custom_config)

        assert manager.config == custom_config
        assert "custom" in manager.config.commands

    @pytest.mark.asyncio
    async def test_setup_commands_auto_with_custom_profile_resolver(self, mock_bot):
        """Test setup with custom profile resolver."""

        def custom_resolver(flags: Flags) -> str:
            return "admin" if flags.is_registered else "guest"

        manager = await setup_commands_auto(mock_bot, profile_resolver=custom_resolver)

        # Test the custom resolver
        flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=False
        )
        result = manager.profile_resolver(flags)
        assert result == "admin"

    @pytest.mark.asyncio
    async def test_setup_commands_auto_calls_setup_all(self, mock_bot):
        """Test that setup_all is called on the manager."""
        with patch.object(
            CommandScopeManager, "setup_all", new_callable=AsyncMock
        ) as mock_setup:
            await setup_commands_auto(mock_bot)
            mock_setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_commands_auto_with_all_parameters(self, mock_bot):
        """Test setup with all parameters provided."""
        languages = ["en", "ru"]
        mock_i18n = Mock()
        custom_config = CmdsConfig(
            languages=languages,
            commands={"test": CommandDef(i18n_key="test.desc")},
        )

        def custom_resolver(flags: Flags) -> str:
            return "test_profile"

        manager = await setup_commands_auto(
            mock_bot,
            languages=languages,
            i18n_instance=mock_i18n,
            config=custom_config,
            profile_resolver=custom_resolver,
        )

        assert manager.config == custom_config
        assert manager.translator is not None
        assert manager.profile_resolver == custom_resolver

    @pytest.mark.asyncio
    async def test_setup_commands_auto_default_languages(self, mock_bot):
        """Test that default languages are used when None provided."""
        manager = await setup_commands_auto(mock_bot, languages=None)

        assert manager.config.languages == ["en"]
        assert manager.config.fallback_language == "en"

    @pytest.mark.asyncio
    async def test_setup_commands_auto_empty_languages_list(self, mock_bot):
        """Test setup with empty languages list."""
        manager = await setup_commands_auto(mock_bot, languages=[])

        # Should fallback to "en" when languages list is empty
        assert manager.config.fallback_language == "en"


class TestTryImportI18n:
    """Test _try_import_i18n function."""

    def test_try_import_i18n_no_imports(self):
        """Test when no i18n modules are available."""
        with patch("builtins.__import__", side_effect=ImportError):
            result = _try_import_i18n()
            assert result is None

    def test_try_import_i18n_successful_import(self):
        """Test successful i18n import."""
        mock_module = Mock()
        mock_module.i18n = Mock()

        with patch("builtins.__import__", return_value=mock_module):
            result = _try_import_i18n()
            assert result == mock_module.i18n

    def test_try_import_i18n_module_with_gettext(self):
        """Test import of module with gettext method."""
        mock_module = Mock()
        mock_module.gettext = Mock()
        # Explicitly remove i18n attribute to test the gettext path
        delattr(mock_module, "i18n")

        with patch("builtins.__import__", return_value=mock_module):
            result = _try_import_i18n()
            assert result is mock_module

    def test_try_import_i18n_import_error_handling(self):
        """Test that import errors are handled gracefully."""

        def mock_import(name, fromlist=None):
            if name == "bot.core.i18n.i18n":
                raise ImportError("Module not found")
            elif name == "bot.i18n.i18n":
                mock_module = Mock()
                mock_module.i18n = Mock()
                return mock_module
            else:
                raise ImportError("Module not found")

        with patch("builtins.__import__", side_effect=mock_import):
            result = _try_import_i18n()
            assert result is not None

    def test_try_import_i18n_all_patterns_fail(self):
        """Test when all import patterns fail."""
        with patch("builtins.__import__", side_effect=ImportError("Not found")):
            result = _try_import_i18n()
            assert result is None


class TestCreateDefaultConfig:
    """Test create_default_config function."""

    def test_create_default_config_basic(self):
        """Test basic default config creation."""
        languages = ["en", "ru"]
        config = create_default_config(languages)

        assert isinstance(config, CmdsConfig)
        assert config.languages == languages
        assert config.fallback_language == "en"
        assert config.i18n_key_prefix == "cmd"

        # Check default commands
        assert "start" in config.commands
        assert "help" in config.commands
        assert "cancel" in config.commands

        # Check default profiles
        assert "guest" in config.profiles
        assert "user" in config.profiles

        # Check default scopes
        assert len(config.scopes) == 1
        assert config.scopes[0].scope == "all_private_chats"
        assert config.scopes[0].profile == "guest"

    def test_create_default_config_single_language(self):
        """Test config creation with single language."""
        languages = ["es"]
        config = create_default_config(languages)

        assert config.languages == ["es"]
        assert config.fallback_language == "es"

    def test_create_default_config_empty_languages(self):
        """Test config creation with empty languages list."""
        languages = []
        config = create_default_config(languages)

        assert config.languages == []
        assert config.fallback_language == "en"  # Should fallback to "en"

    def test_create_default_config_command_definitions(self):
        """Test that command definitions are properly created."""
        config = create_default_config(["en"])

        start_cmd = config.commands["start"]
        help_cmd = config.commands["help"]
        cancel_cmd = config.commands["cancel"]

        assert isinstance(start_cmd, CommandDef)
        assert isinstance(help_cmd, CommandDef)
        assert isinstance(cancel_cmd, CommandDef)

        assert start_cmd.i18n_key == "start.desc"
        assert help_cmd.i18n_key == "help.desc"
        assert cancel_cmd.i18n_key == "cancel.desc"

    def test_create_default_config_profile_definitions(self):
        """Test that profile definitions are properly created."""
        config = create_default_config(["en"])

        guest_profile = config.profiles["guest"]
        user_profile = config.profiles["user"]

        assert isinstance(guest_profile, ProfileDef)
        assert isinstance(user_profile, ProfileDef)

        assert guest_profile.include == ["start", "help"]
        assert user_profile.include == ["start", "help", "cancel"]

    def test_create_default_config_scope_definitions(self):
        """Test that scope definitions are properly created."""
        config = create_default_config(["en"])

        scope = config.scopes[0]
        assert isinstance(scope, ScopeDef)
        assert scope.scope == "all_private_chats"
        assert scope.profile == "guest"

    def test_create_default_config_menu_button(self):
        """Test that menu button is properly configured."""
        config = create_default_config(["en"])

        assert isinstance(config.menu_button, MenuButtonDef)
        assert config.menu_button.mode == "commands"


class TestCreateDefaultProfileResolver:
    """Test create_default_profile_resolver function."""

    def test_create_default_profile_resolver_basic(self):
        """Test basic profile resolver creation."""
        resolver = create_default_profile_resolver()

        assert callable(resolver)

    def test_default_profile_resolver_guest_user(self):
        """Test resolver returns 'guest' for unregistered users."""
        resolver = create_default_profile_resolver()

        # Unregistered user
        flags = Flags(
            is_registered=False, has_vehicle=False, is_during_registration=False
        )
        result = resolver(flags)
        assert result == "guest"

        # User during registration
        flags = Flags(
            is_registered=False, has_vehicle=False, is_during_registration=True
        )
        result = resolver(flags)
        assert result == "guest"

    def test_default_profile_resolver_registered_user(self):
        """Test resolver returns 'user' for registered users."""
        resolver = create_default_profile_resolver()

        # Registered user
        flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=False
        )
        result = resolver(flags)
        assert result == "user"

        # Registered user with vehicle
        flags = Flags(
            is_registered=True, has_vehicle=True, is_during_registration=False
        )
        result = resolver(flags)
        assert result == "user"

    def test_default_profile_resolver_during_registration(self):
        """Test resolver behavior during registration."""
        resolver = create_default_profile_resolver()

        # Even if registered, during registration should return guest
        flags = Flags(is_registered=True, has_vehicle=True, is_during_registration=True)
        result = resolver(flags)
        assert result == "guest"

    def test_default_profile_resolver_edge_cases(self):
        """Test resolver with various flag combinations."""
        resolver = create_default_profile_resolver()

        # All combinations
        test_cases = [
            (False, False, False, "guest"),
            (False, False, True, "guest"),
            (False, True, False, "guest"),
            (False, True, True, "guest"),
            (True, False, False, "user"),
            (True, False, True, "guest"),  # During registration overrides
            (True, True, False, "user"),
            (True, True, True, "guest"),  # During registration overrides
        ]

        for is_registered, has_vehicle, is_during_registration, expected in test_cases:
            flags = Flags(
                is_registered=is_registered,
                has_vehicle=has_vehicle,
                is_during_registration=is_during_registration,
            )
            result = resolver(flags)
            assert result == expected, f"Failed for flags: {flags}"


class TestAutoSetupIntegration:
    """Integration tests for auto_setup functionality."""

    @pytest.mark.asyncio
    async def test_full_auto_setup_workflow(self, mock_bot):
        """Test complete auto setup workflow."""
        # Mock i18n instance
        mock_i18n = Mock()
        mock_i18n.gettext.return_value = "Translated command"
        # Mock with_locale context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_context)
        mock_context.__exit__ = Mock(return_value=None)
        mock_i18n.with_locale.return_value = mock_context

        # Setup with all defaults
        manager = await setup_commands_auto(mock_bot, i18n_instance=mock_i18n)

        # Verify manager is properly configured
        assert isinstance(manager, CommandScopeManager)
        assert manager.bot == mock_bot
        assert manager.config is not None
        assert manager.translator is not None
        assert manager.profile_resolver is not None

        # Test translator works
        result = manager.translator("test.key", locale="en")
        assert result == "Translated command"

        # Test profile resolver works
        flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=False
        )
        profile = manager.profile_resolver(flags)
        assert profile == "user"

    @pytest.mark.asyncio
    async def test_auto_setup_with_custom_everything(self, mock_bot):
        """Test auto setup with all custom components."""
        # Custom languages
        languages = ["en", "ru", "es", "fr"]

        # Custom i18n
        mock_i18n = Mock()
        mock_i18n.gettext.return_value = "Custom translation"

        # Custom config
        custom_config = CmdsConfig(
            languages=languages,
            commands={
                "custom1": CommandDef(i18n_key="custom1.desc"),
                "custom2": CommandDef(i18n_key="custom2.desc"),
            },
            profiles={
                "admin": ProfileDef(include=["custom1", "custom2"]),
                "moderator": ProfileDef(include=["custom1"]),
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="admin"),
            ],
        )

        # Custom profile resolver
        def custom_resolver(flags: Flags) -> str:
            if flags.is_registered and flags.has_vehicle:
                return "admin"
            elif flags.is_registered:
                return "moderator"
            else:
                return "guest"

        manager = await setup_commands_auto(
            mock_bot,
            languages=languages,
            i18n_instance=mock_i18n,
            config=custom_config,
            profile_resolver=custom_resolver,
        )

        # Verify all custom components are used
        assert manager.config == custom_config
        assert manager.translator is not None
        assert manager.profile_resolver == custom_resolver

        # Test custom profile resolver
        admin_flags = Flags(
            is_registered=True, has_vehicle=True, is_during_registration=False
        )
        moderator_flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=False
        )
        guest_flags = Flags(
            is_registered=False, has_vehicle=False, is_during_registration=False
        )

        assert manager.profile_resolver(admin_flags) == "admin"
        assert manager.profile_resolver(moderator_flags) == "moderator"
        assert manager.profile_resolver(guest_flags) == "guest"
