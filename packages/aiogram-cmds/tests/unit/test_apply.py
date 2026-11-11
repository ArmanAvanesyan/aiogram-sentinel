"""
Unit tests for the apply module.
"""

from unittest.mock import Mock

import pytest
from aiogram.types import (
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
    BotCommandScopeChatMember,
    BotCommandScopeDefault,
    MenuButtonCommands,
    MenuButtonDefault,
)

from aiogram_cmds.apply import (
    _scope_obj,
    _sorted_scopes,
    apply_config,
)
from aiogram_cmds.customize import (
    CmdsConfig,
    CommandDef,
    MenuButtonDef,
    ProfileDef,
    ScopeDef,
)


class TestScopeObj:
    """Test _scope_obj function."""

    def test_scope_obj_default(self):
        """Test default scope."""
        scope_def = ScopeDef(scope="default", profile="user")
        result = _scope_obj(scope_def)
        assert isinstance(result, BotCommandScopeDefault)

    def test_scope_obj_all_private_chats(self):
        """Test all private chats scope."""
        scope_def = ScopeDef(scope="all_private_chats", profile="user")
        result = _scope_obj(scope_def)
        assert isinstance(result, BotCommandScopeAllPrivateChats)

    def test_scope_obj_all_group_chats(self):
        """Test all group chats scope."""
        scope_def = ScopeDef(scope="all_group_chats", profile="user")
        result = _scope_obj(scope_def)
        assert isinstance(result, BotCommandScopeAllGroupChats)

    def test_scope_obj_all_chat_admins(self):
        """Test all chat administrators scope."""
        scope_def = ScopeDef(scope="all_chat_admins", profile="user")
        result = _scope_obj(scope_def)
        assert isinstance(result, BotCommandScopeAllChatAdministrators)

    def test_scope_obj_chat(self):
        """Test chat scope."""
        scope_def = ScopeDef(scope="chat", profile="user", chat_id=12345)
        result = _scope_obj(scope_def)
        assert isinstance(result, BotCommandScopeChat)
        assert result.chat_id == 12345

    def test_scope_obj_chat_admins(self):
        """Test chat administrators scope."""
        scope_def = ScopeDef(scope="chat_admins", profile="user", chat_id=12345)
        result = _scope_obj(scope_def)
        assert isinstance(result, BotCommandScopeChatAdministrators)
        assert result.chat_id == 12345

    def test_scope_obj_chat_member(self):
        """Test chat member scope."""
        scope_def = ScopeDef(
            scope="chat_member", profile="user", chat_id=12345, user_id=67890
        )
        result = _scope_obj(scope_def)
        assert isinstance(result, BotCommandScopeChatMember)
        assert result.chat_id == 12345
        assert result.user_id == 67890

    def test_scope_obj_unknown_scope(self):
        """Test unknown scope raises ValueError."""
        # Create a scope_def with an invalid scope by bypassing validation
        scope_def = ScopeDef(scope="default", profile="user")
        # Manually set the scope to an invalid value
        scope_def.scope = "unknown_scope"
        with pytest.raises(ValueError, match="Unknown scope: unknown_scope"):
            _scope_obj(scope_def)

    def test_scope_obj_chat_without_chat_id(self):
        """Test chat scope without chat_id raises error."""
        scope_def = ScopeDef(scope="chat", profile="user", chat_id=None)
        # BotCommandScopeChat requires a valid chat_id, so this should raise an error
        with pytest.raises(
            (ValueError, TypeError)
        ):  # ValidationError from pydantic or aiogram
            _scope_obj(scope_def)

    def test_scope_obj_chat_member_without_ids(self):
        """Test chat member scope without chat_id and user_id raises error."""
        scope_def = ScopeDef(
            scope="chat_member", profile="user", chat_id=None, user_id=None
        )
        # BotCommandScopeChatMember requires valid chat_id and user_id, so this should raise an error
        with pytest.raises(
            (ValueError, TypeError)
        ):  # ValidationError from pydantic or aiogram
            _scope_obj(scope_def)


class TestSortedScopes:
    """Test _sorted_scopes function."""

    def test_sorted_scopes_basic(self):
        """Test basic scope sorting."""
        scopes = [
            ScopeDef(scope="default", profile="user"),
            ScopeDef(scope="chat_member", profile="user", chat_id=1, user_id=1),
            ScopeDef(scope="all_private_chats", profile="user"),
            ScopeDef(scope="chat", profile="user", chat_id=1),
        ]

        sorted_result = _sorted_scopes(scopes)

        # Should be sorted by specificity (most specific first)
        assert sorted_result[0].scope == "chat_member"
        assert sorted_result[1].scope == "chat"
        assert sorted_result[2].scope == "all_private_chats"
        assert sorted_result[3].scope == "default"

    def test_sorted_scopes_all_types(self):
        """Test sorting with all scope types."""
        scopes = [
            ScopeDef(scope="default", profile="user"),
            ScopeDef(scope="all_private_chats", profile="user"),
            ScopeDef(scope="all_group_chats", profile="user"),
            ScopeDef(scope="all_chat_admins", profile="user"),
            ScopeDef(scope="chat", profile="user", chat_id=1),
            ScopeDef(scope="chat_admins", profile="user", chat_id=1),
            ScopeDef(scope="chat_member", profile="user", chat_id=1, user_id=1),
        ]

        sorted_result = _sorted_scopes(scopes)

        # Verify order (most specific to least specific)
        expected_order = [
            "chat_member",
            "chat_admins",
            "chat",
            "all_chat_admins",
            "all_group_chats",
            "all_private_chats",
            "default",
        ]

        actual_order = [s.scope for s in sorted_result]
        assert actual_order == expected_order

    def test_sorted_scopes_empty(self):
        """Test sorting empty list."""
        result = _sorted_scopes([])
        assert result == []

    def test_sorted_scopes_single_scope(self):
        """Test sorting single scope."""
        scopes = [ScopeDef(scope="chat", profile="user", chat_id=123)]
        result = _sorted_scopes(scopes)
        assert len(result) == 1
        assert result[0].scope == "chat"
        assert result[0].chat_id == 123

    def test_sorted_scopes_duplicates(self):
        """Test sorting with duplicate scopes."""
        scopes = [
            ScopeDef(scope="chat", profile="user", chat_id=1),
            ScopeDef(scope="chat", profile="user", chat_id=2),
            ScopeDef(scope="default", profile="user"),
        ]

        result = _sorted_scopes(scopes)

        # Both chat scopes should come before default
        assert result[0].scope == "chat"
        assert result[1].scope == "chat"
        assert result[2].scope == "default"

        # Order of duplicates should be preserved
        assert result[0].chat_id == 1
        assert result[1].chat_id == 2


class TestApplyConfig:
    """Test apply_config function."""

    @pytest.mark.asyncio
    async def test_apply_config_basic(self, mock_bot):
        """Test basic config application."""
        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
            menu_button=MenuButtonDef(mode="commands"),
        )

        await apply_config(mock_bot, config)

        # Should call set_my_commands once for the scope
        mock_bot.set_my_commands.assert_called_once()
        # Should call set_chat_menu_button once
        mock_bot.set_chat_menu_button.assert_called_once_with(
            menu_button=MenuButtonCommands()
        )

    @pytest.mark.asyncio
    async def test_apply_config_multiple_languages(self, mock_bot):
        """Test config application with multiple languages."""
        config = CmdsConfig(
            languages=["en", "ru"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
        )

        await apply_config(mock_bot, config)

        # Should call set_my_commands twice (once for each language)
        assert mock_bot.set_my_commands.call_count == 2

    @pytest.mark.asyncio
    async def test_apply_config_multiple_scopes(self, mock_bot):
        """Test config application with multiple scopes."""
        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[
                ScopeDef(scope="all_private_chats", profile="user"),
                ScopeDef(scope="all_group_chats", profile="user"),
            ],
        )

        await apply_config(mock_bot, config)

        # Should call set_my_commands twice (once for each scope)
        assert mock_bot.set_my_commands.call_count == 2

    @pytest.mark.asyncio
    async def test_apply_config_with_translator(self, mock_bot):
        """Test config application with translator."""
        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
        )

        mock_translator = Mock()
        mock_translator.return_value = "Translated start"

        await apply_config(mock_bot, config, translator=mock_translator)

        # Should call set_my_commands
        mock_bot.set_my_commands.assert_called_once()
        # Translator should be used
        mock_translator.assert_called()

    @pytest.mark.asyncio
    async def test_apply_config_menu_button_commands(self, mock_bot):
        """Test config application with commands menu button."""
        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
            menu_button=MenuButtonDef(mode="commands"),
        )

        await apply_config(mock_bot, config)

        mock_bot.set_chat_menu_button.assert_called_once_with(
            menu_button=MenuButtonCommands()
        )

    @pytest.mark.asyncio
    async def test_apply_config_menu_button_default(self, mock_bot):
        """Test config application with default menu button."""
        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
            menu_button=MenuButtonDef(mode="default"),
        )

        await apply_config(mock_bot, config)

        mock_bot.set_chat_menu_button.assert_called_once_with(
            menu_button=MenuButtonDefault()
        )

    @pytest.mark.asyncio
    async def test_apply_config_scope_specific_languages(self, mock_bot):
        """Test config application with scope-specific languages."""
        config = CmdsConfig(
            languages=["en", "ru"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[
                ScopeDef(scope="all_private_chats", profile="user", languages=["en"]),
                ScopeDef(scope="all_group_chats", profile="user", languages=["ru"]),
            ],
        )

        await apply_config(mock_bot, config)

        # Should call set_my_commands twice (once for each scope with its specific language)
        assert mock_bot.set_my_commands.call_count == 2

    @pytest.mark.asyncio
    async def test_apply_config_empty_languages(self, mock_bot):
        """Test config application with empty languages list."""
        config = CmdsConfig(
            languages=[],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
        )

        await apply_config(mock_bot, config)

        # Should still call set_my_commands with default "en" language
        mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_config_no_scopes(self, mock_bot):
        """Test config application with no scopes."""
        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[],
        )

        await apply_config(mock_bot, config)

        # Should not call set_my_commands
        mock_bot.set_my_commands.assert_not_called()
        # Should still call set_chat_menu_button
        mock_bot.set_chat_menu_button.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_config_complex_setup(self, mock_bot):
        """Test complex config application with multiple scopes and languages."""
        config = CmdsConfig(
            languages=["en", "ru", "es"],
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
                ScopeDef(scope="chat_member", chat_id=1, user_id=1, profile="admin"),
                ScopeDef(scope="chat", chat_id=1, profile="user"),
                ScopeDef(scope="all_private_chats", profile="user"),
                ScopeDef(scope="default", profile="user"),
            ],
            menu_button=MenuButtonDef(mode="commands"),
        )

        await apply_config(mock_bot, config)

        # Should call set_my_commands for each scope * each language
        # 4 scopes * 3 languages = 12 calls
        assert mock_bot.set_my_commands.call_count == 12
        # Should call set_chat_menu_button once
        mock_bot.set_chat_menu_button.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_config_scope_ordering(self, mock_bot):
        """Test that scopes are applied in correct order (most specific first)."""
        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[
                ScopeDef(scope="default", profile="user"),
                ScopeDef(scope="chat_member", chat_id=1, user_id=1, profile="user"),
                ScopeDef(scope="all_private_chats", profile="user"),
            ],
        )

        await apply_config(mock_bot, config)

        # Verify calls were made in the correct order
        calls = mock_bot.set_my_commands.call_args_list

        # First call should be for chat_member (most specific)
        first_scope = calls[0][1]["scope"]
        assert isinstance(first_scope, BotCommandScopeChatMember)

        # Second call should be for all_private_chats
        second_scope = calls[1][1]["scope"]
        assert isinstance(second_scope, BotCommandScopeAllPrivateChats)

        # Third call should be for default (least specific)
        third_scope = calls[2][1]["scope"]
        assert isinstance(third_scope, BotCommandScopeDefault)

    @pytest.mark.asyncio
    async def test_apply_config_with_registry(self, mock_bot):
        """Test that CommandRegistry is properly used."""
        config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
        )

        await apply_config(mock_bot, config)

        # Verify that set_my_commands was called with proper arguments
        mock_bot.set_my_commands.assert_called_once()
        call_args = mock_bot.set_my_commands.call_args

        # Should have commands as first argument, scope and language_code as kwargs
        assert len(call_args[0]) == 1  # commands as first argument
        assert "scope" in call_args[1]
        assert "language_code" in call_args[1]
        assert call_args[1]["language_code"] == "en"
        assert isinstance(call_args[1]["scope"], BotCommandScopeAllPrivateChats)
