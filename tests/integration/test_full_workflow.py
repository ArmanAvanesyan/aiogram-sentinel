"""
Integration tests for aiogram-cmds library.

These tests verify complete workflows and interactions between components,
ensuring the library works correctly in real-world scenarios.
"""

from contextlib import contextmanager, nullcontext
from unittest.mock import Mock

import pytest
from aiogram.types import (
    MenuButtonCommands,
)

from aiogram_cmds import (
    CmdsSettings,
    CommandScopeManager,
    Flags,
    build_translator_from_i18n,
    setup_commands_auto,
)
from aiogram_cmds.customize import (
    CmdsConfig,
    CommandDef,
    MenuButtonDef,
    ProfileDef,
    ScopeDef,
)


class TestFullWorkflowIntegration:
    """Test complete workflows from setup to command management."""

    @pytest.mark.asyncio
    async def test_simple_mode_full_workflow(self, mock_bot):
        """Test complete simple mode workflow."""
        # Setup manager with simple mode
        settings = CmdsSettings(
            languages=["en", "ru"],
            fallback_language="en",
            i18n_key_prefix="bot",
        )

        manager = CommandScopeManager(
            bot=mock_bot,
            settings=settings,
        )

        # Setup all command scopes
        await manager.setup_all()

        # Verify setup calls
        assert mock_bot.set_my_commands.call_count >= 3  # default + 2 languages
        mock_bot.set_chat_menu_button.assert_called_once()

        # Update user commands for different scenarios
        await manager.update_user_commands(
            user_id=12345,
            is_registered=False,
            has_vehicle=False,
            is_during_registration=False,
            user_language="en",
        )

        await manager.update_user_commands(
            user_id=67890,
            is_registered=True,
            has_vehicle=True,
            is_during_registration=False,
            user_language="ru",
        )

        # Clear user commands
        await manager.clear_user_commands(user_id=12345)

        # Verify all operations were called
        assert mock_bot.set_my_commands.call_count >= 5  # setup + 2 users
        mock_bot.delete_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_advanced_mode_full_workflow(self, mock_bot):
        """Test complete advanced mode workflow with custom config."""
        # Create custom configuration
        config = CmdsConfig(
            languages=["en", "ru", "es"],
            fallback_language="en",
            i18n_key_prefix="bot",
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "profile": CommandDef(i18n_key="profile.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
                "settings": CommandDef(i18n_key="settings.desc"),
            },
            profiles={
                "guest": ProfileDef(include=["start", "help"]),
                "user": ProfileDef(include=["start", "help", "profile", "settings"]),
                "admin": ProfileDef(
                    include=["start", "help", "profile", "admin", "settings"]
                ),
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="guest"),
                ScopeDef(scope="chat", profile="user", chat_id=12345),
                ScopeDef(
                    scope="chat_member", profile="admin", chat_id=12345, user_id=67890
                ),
            ],
            menu_button=MenuButtonDef(mode="commands"),
        )

        # Create custom profile resolver
        def custom_resolver(flags: Flags) -> str:
            if flags.is_registered and flags.has_vehicle:
                return "admin"
            elif flags.is_registered:
                return "user"
            else:
                return "guest"

        # Setup manager with advanced mode
        manager = CommandScopeManager(
            bot=mock_bot,
            config=config,
            profile_resolver=custom_resolver,
        )

        # Setup all command scopes
        await manager.setup_all()

        # Verify complex setup calls
        # Should call set_my_commands for each scope * each language
        expected_calls = len(config.scopes) * len(config.languages)
        assert mock_bot.set_my_commands.call_count == expected_calls
        mock_bot.set_chat_menu_button.assert_called_once_with(
            menu_button=MenuButtonCommands()
        )

        # Test profile resolution
        admin_flags = Flags(
            is_registered=True, has_vehicle=True, is_during_registration=False
        )
        user_flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=False
        )
        guest_flags = Flags(
            is_registered=False, has_vehicle=False, is_during_registration=False
        )

        assert manager.profile_resolver(admin_flags) == "admin"
        assert manager.profile_resolver(user_flags) == "user"
        assert manager.profile_resolver(guest_flags) == "guest"

    @pytest.mark.asyncio
    async def test_auto_setup_integration(self, mock_bot):
        """Test auto-setup integration workflow."""
        # Mock i18n instance
        mock_i18n = Mock()
        mock_i18n.gettext.return_value = "Translated command"
        mock_i18n.with_locale.side_effect = lambda locale: nullcontext()

        # Use auto-setup
        manager = await setup_commands_auto(
            bot=mock_bot,
            languages=["en", "ru"],
            i18n_instance=mock_i18n,
        )

        # Verify manager is properly configured
        assert isinstance(manager, CommandScopeManager)
        assert manager.bot == mock_bot
        assert manager.config is not None
        assert manager.translator is not None
        assert manager.profile_resolver is not None

        # Verify setup was called
        assert mock_bot.set_my_commands.call_count >= 2  # default + languages
        mock_bot.set_chat_menu_button.assert_called_once()

        # Test translator integration
        result = manager.translator("test.key", locale="en")
        assert result == "Translated command"

    @pytest.mark.asyncio
    async def test_i18n_integration_workflow(self, mock_bot):
        """Test complete i18n integration workflow."""
        # Create mock i18n with realistic translations
        mock_i18n = Mock()

        current_locale = "en"

        @contextmanager
        def with_locale(locale):
            nonlocal current_locale
            previous = current_locale
            current_locale = locale
            try:
                yield
            finally:
                current_locale = previous

        mock_i18n.with_locale.side_effect = with_locale

        def mock_gettext(key):
            translations = {
                ("bot.start.desc", "en"): "Start the bot",
                ("bot.start.desc", "ru"): "Запустить бота",
                ("bot.help.desc", "en"): "Get help",
                ("bot.help.desc", "ru"): "Получить помощь",
                ("bot.profile.desc", "en"): "View profile",
                ("bot.profile.desc", "ru"): "Просмотр профиля",
            }
            return translations.get((key, current_locale), key)

        mock_i18n.gettext.side_effect = mock_gettext

        # Build translator
        translator = build_translator_from_i18n(mock_i18n)

        # Test translator
        assert translator("bot.start.desc", locale="en") == "Start the bot"
        assert translator("bot.start.desc", locale="ru") == "Запустить бота"
        assert translator("bot.help.desc", locale="en") == "Get help"
        assert translator("bot.help.desc", locale="ru") == "Получить помощь"

        # Test with manager
        settings = CmdsSettings(
            languages=["en", "ru"],
            i18n_key_prefix="bot",
        )

        manager = CommandScopeManager(
            bot=mock_bot,
            settings=settings,
            translator=translator,
        )

        await manager.setup_all()

        # Verify translator was used
        mock_i18n.gettext.assert_called()

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, mock_bot):
        """Test error handling in complete workflows."""
        # Make bot methods raise exceptions
        mock_bot.set_my_commands.side_effect = Exception("API Error")
        mock_bot.delete_my_commands.side_effect = Exception("API Error")
        mock_bot.set_chat_menu_button.side_effect = Exception("API Error")

        manager = CommandScopeManager(bot=mock_bot)

        with pytest.raises(Exception, match="API Error"):
            await manager.setup_all()
        with pytest.raises(Exception, match="API Error"):
            await manager.update_user_commands(12345, True, False)
        with pytest.raises(Exception, match="API Error"):
            await manager.clear_user_commands(12345)


class TestMultiLanguageIntegration:
    """Test multi-language support integration."""

    @pytest.mark.asyncio
    async def test_multi_language_setup(self, mock_bot):
        """Test setup with multiple languages."""
        languages = ["en", "ru", "es", "fr", "de"]

        config = CmdsConfig(
            languages=languages,
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)
        await manager.setup_all()

        # Should call set_my_commands for each language
        assert mock_bot.set_my_commands.call_count == len(languages)

    @pytest.mark.asyncio
    async def test_language_specific_user_commands(self, mock_bot):
        """Test user commands with different languages."""
        manager = CommandScopeManager(bot=mock_bot)

        # Test different languages for same user
        languages = ["en", "ru", "es"]

        for lang in languages:
            await manager.update_user_commands(
                user_id=12345,
                is_registered=True,
                has_vehicle=False,
                is_during_registration=False,
                user_language=lang,
            )

        # Should call set_my_commands for each language
        assert mock_bot.set_my_commands.call_count == len(languages)


class TestProfileSystemIntegration:
    """Test profile system integration."""

    @pytest.mark.asyncio
    async def test_complex_profile_hierarchy(self, mock_bot):
        """Test complex profile hierarchy with inheritance patterns."""
        config = CmdsConfig(
            languages=["en"],
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "profile": CommandDef(i18n_key="profile.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
                "settings": CommandDef(i18n_key="settings.desc"),
                "logout": CommandDef(i18n_key="logout.desc"),
            },
            profiles={
                "base": ProfileDef(include=["start", "help"]),
                "user": ProfileDef(include=["start", "help", "profile", "settings"]),
                "moderator": ProfileDef(include=["start", "help", "profile", "admin"]),
                "admin": ProfileDef(
                    include=["start", "help", "profile", "admin", "settings", "logout"]
                ),
                "limited_admin": ProfileDef(
                    include=["start", "help", "profile", "admin", "settings"],
                    exclude=["admin"],
                ),
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="base"),
            ],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)
        await manager.setup_all()

        # Test profile resolution
        registry = manager.config.profiles

        # Verify profile configurations
        assert len(registry["base"].include) == 2
        assert len(registry["user"].include) == 4
        assert len(registry["moderator"].include) == 4
        assert len(registry["admin"].include) == 6
        assert len(registry["limited_admin"].exclude) == 1

    @pytest.mark.asyncio
    async def test_dynamic_profile_switching(self, mock_bot):
        """Test dynamic profile switching for users."""
        config = CmdsConfig(
            languages=["en"],
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
            },
            profiles={
                "user": ProfileDef(include=["start", "help"]),
                "admin": ProfileDef(include=["start", "help", "admin"]),
            },
            scopes=[
                ScopeDef(
                    scope="chat_member", profile="user", chat_id=12345, user_id=67890
                ),
            ],
        )

        # Custom resolver that can change based on external state
        class DynamicResolver:
            def __init__(self):
                self.user_roles = {67890: "user"}

            def __call__(self, flags: Flags) -> str:
                # Simulate role checking
                if flags.is_registered and flags.has_vehicle:
                    return "admin"
                return "user"

            def promote_user(self, user_id: int):
                self.user_roles[user_id] = "admin"

        resolver = DynamicResolver()
        CommandScopeManager(bot=mock_bot, config=config, profile_resolver=resolver)

        # Test initial state
        flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=False
        )
        assert resolver(flags) == "user"

        # Test promoted state
        flags = Flags(
            is_registered=True, has_vehicle=True, is_during_registration=False
        )
        assert resolver(flags) == "admin"


class TestScopeHierarchyIntegration:
    """Test scope hierarchy and precedence integration."""

    @pytest.mark.asyncio
    async def test_scope_precedence_workflow(self, mock_bot):
        """Test scope precedence in complex scenarios."""
        config = CmdsConfig(
            languages=["en"],
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
            },
            profiles={
                "guest": ProfileDef(include=["start", "help"]),
                "user": ProfileDef(include=["start", "help", "admin"]),
            },
            scopes=[
                # Most specific first
                ScopeDef(
                    scope="chat_member", profile="user", chat_id=12345, user_id=67890
                ),
                ScopeDef(scope="chat", profile="guest", chat_id=12345),
                ScopeDef(scope="all_private_chats", profile="guest"),
                ScopeDef(scope="default", profile="guest"),
            ],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)
        await manager.setup_all()

        # Verify scopes are applied in correct order (most specific first)
        calls = mock_bot.set_my_commands.call_args_list

        # First call should be for chat_member (most specific)
        first_scope = calls[0][1]["scope"]
        assert first_scope.chat_id == 12345
        assert first_scope.user_id == 67890

        # Second call should be for chat
        second_scope = calls[1][1]["scope"]
        assert second_scope.chat_id == 12345

        # Third call should be for all_private_chats
        third_scope = calls[2][1]["scope"]
        assert hasattr(third_scope, "type")  # BotCommandScopeAllPrivateChats

        # Fourth call should be for default
        fourth_scope = calls[3][1]["scope"]
        assert hasattr(fourth_scope, "type")  # BotCommandScopeDefault


class TestPerformanceIntegration:
    """Test performance characteristics in realistic scenarios."""

    @pytest.mark.asyncio
    async def test_large_scale_setup(self, mock_bot):
        """Test setup with large number of commands and profiles."""
        # Create large configuration
        commands = {}
        profiles = {}

        # 50 commands
        for i in range(50):
            commands[f"cmd_{i}"] = CommandDef(i18n_key=f"cmd_{i}.desc")

        # 10 profiles with different command sets
        for i in range(10):
            include_commands = [f"cmd_{j}" for j in range(i * 5, (i + 1) * 5)]
            profiles[f"profile_{i}"] = ProfileDef(include=include_commands)

        config = CmdsConfig(
            languages=["en", "ru"],
            commands=commands,
            profiles=profiles,
            scopes=[
                ScopeDef(scope="all_private_chats", profile="profile_0"),
            ],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)

        # Should handle large config without issues
        await manager.setup_all()

        # Verify setup completed
        assert mock_bot.set_my_commands.call_count >= 2  # At least 2 languages

    @pytest.mark.asyncio
    async def test_rapid_user_updates(self, mock_bot):
        """Test rapid user command updates."""
        manager = CommandScopeManager(bot=mock_bot)

        # Simulate rapid updates for many users
        for user_id in range(100):
            await manager.update_user_commands(
                user_id=user_id,
                is_registered=user_id % 2 == 0,
                has_vehicle=user_id % 3 == 0,
                is_during_registration=user_id % 5 == 0,
                user_language="en",
            )

        # Should handle all updates
        assert mock_bot.set_my_commands.call_count == 100


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    @pytest.mark.asyncio
    async def test_ecommerce_bot_scenario(self, mock_bot):
        """Test e-commerce bot scenario with user states."""
        config = CmdsConfig(
            languages=["en", "ru"],
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "catalog": CommandDef(i18n_key="catalog.desc"),
                "cart": CommandDef(i18n_key="cart.desc"),
                "profile": CommandDef(i18n_key="profile.desc"),
                "orders": CommandDef(i18n_key="orders.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
            },
            profiles={
                "visitor": ProfileDef(include=["start", "catalog"]),
                "customer": ProfileDef(include=["start", "catalog", "cart", "profile"]),
                "registered": ProfileDef(
                    include=["start", "catalog", "cart", "profile", "orders"]
                ),
                "admin": ProfileDef(
                    include=["start", "catalog", "cart", "profile", "orders", "admin"]
                ),
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="visitor"),
            ],
        )

        def ecommerce_resolver(flags: Flags) -> str:
            if flags.is_registered and flags.has_vehicle:  # has_vehicle = is_admin
                return "admin"
            elif flags.is_registered:
                return "registered"
            elif flags.is_during_registration:
                return "customer"
            else:
                return "visitor"

        manager = CommandScopeManager(
            bot=mock_bot,
            config=config,
            profile_resolver=ecommerce_resolver,
        )

        await manager.setup_all()

        # Test different user states
        visitor_flags = Flags(
            is_registered=False, has_vehicle=False, is_during_registration=False
        )
        customer_flags = Flags(
            is_registered=False, has_vehicle=False, is_during_registration=True
        )
        registered_flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=False
        )
        admin_flags = Flags(
            is_registered=True, has_vehicle=True, is_during_registration=False
        )

        assert manager.profile_resolver(visitor_flags) == "visitor"
        assert manager.profile_resolver(customer_flags) == "customer"
        assert manager.profile_resolver(registered_flags) == "registered"
        assert manager.profile_resolver(admin_flags) == "admin"

    @pytest.mark.asyncio
    async def test_support_bot_scenario(self, mock_bot):
        """Test customer support bot scenario."""
        config = CmdsConfig(
            languages=["en", "es"],
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "ticket": CommandDef(i18n_key="ticket.desc"),
                "status": CommandDef(i18n_key="status.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
            },
            profiles={
                "user": ProfileDef(include=["start", "help", "ticket", "status"]),
                "agent": ProfileDef(
                    include=["start", "help", "ticket", "status", "admin"]
                ),
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="user"),
                ScopeDef(scope="chat", profile="agent", chat_id=12345),  # Support chat
            ],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)
        await manager.setup_all()

        # Test user in general chat
        await manager.update_user_commands(
            user_id=11111,
            is_registered=True,
            has_vehicle=False,
            is_during_registration=False,
            user_language="en",
        )

        # Test agent in support chat
        await manager.update_user_commands(
            user_id=22222,
            is_registered=True,
            has_vehicle=True,  # has_vehicle = is_agent
            is_during_registration=False,
            user_language="en",
            chat_id=12345,
        )

        # Verify both operations completed
        assert mock_bot.set_my_commands.call_count >= 4  # setup + 2 users
