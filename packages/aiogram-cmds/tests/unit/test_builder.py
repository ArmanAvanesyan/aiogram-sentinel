"""
Unit tests for the command builder module.
"""

import pytest
from aiogram.types import BotCommand

from aiogram_cmds.builder import build_bot_commands, validate_name


class TestCommandNameValidation:
    """Test command name validation."""

    def test_valid_command_names(self):
        """Test that valid command names pass validation."""
        valid_names = [
            "start",
            "help",
            "profile",
            "admin_panel",
            "user123",
            "cmd",
            "a",
            "very_long_command_name_but_valid",
        ]

        for name in valid_names:
            result = validate_name(name)
            assert result == name.lower()

    def test_invalid_command_names(self):
        """Test that invalid command names are corrected."""
        test_cases = [
            ("Start", "start"),  # Uppercase
            ("HELP", "help"),  # All uppercase
            ("My Command", "my_command"),  # Spaces
            ("my-command", "mycommand"),  # Hyphens
            ("123start", "start"),  # Starts with number
            ("start!", "start"),  # Special characters
            ("", "cmd"),  # Empty string
            ("a" * 50, "a" * 32),  # Too long
        ]

        for input_name, expected in test_cases:
            result = validate_name(input_name)
            assert result == expected

    def test_edge_cases(self):
        """Test edge cases for command name validation."""
        edge_cases = [
            (None, "cmd"),
            ("   ", "cmd"),
            ("!!!", "cmd"),
            ("123", "cmd"),
            ("a" * 100, "a" * 32),
        ]

        for input_name, expected in edge_cases:
            result = validate_name(input_name)
            assert result == expected


class TestBuildBotCommands:
    """Test bot command building."""

    def test_build_commands_without_translator(self):
        """Test building commands without a translator."""
        command_names = ["start", "help", "profile"]

        commands = build_bot_commands(command_names, lang="en")

        assert len(commands) == 3
        assert all(isinstance(cmd, BotCommand) for cmd in commands)

        # Check command names
        cmd_names = [cmd.command for cmd in commands]
        assert "start" in cmd_names
        assert "help" in cmd_names
        assert "profile" in cmd_names

        # Check descriptions (should be Title Case)
        descriptions = [cmd.description for cmd in commands]
        assert "Start" in descriptions
        assert "Help" in descriptions
        assert "Profile" in descriptions

    def test_build_commands_with_translator(self, mock_translator):
        """Test building commands with a translator."""
        command_names = ["start", "help", "profile"]

        commands = build_bot_commands(
            command_names, lang="en", translator=mock_translator
        )

        assert len(commands) == 3

        # Check descriptions from translator
        descriptions = [cmd.description for cmd in commands]
        assert "Start the bot" in descriptions
        assert "Show help information" in descriptions
        assert "View your profile" in descriptions

    def test_build_commands_with_custom_prefix(self, mock_translator):
        """Test building commands with custom i18n prefix."""
        command_names = ["start", "help"]

        commands = build_bot_commands(
            command_names, lang="en", translator=mock_translator, key_prefix="bot"
        )

        # Should still work with default prefix since translator is mocked
        assert len(commands) == 2

    def test_build_commands_multiple_languages(self, mock_translator):
        """Test building commands for multiple languages."""
        command_names = ["start", "help"]

        # English
        en_commands = build_bot_commands(
            command_names, lang="en", translator=mock_translator
        )

        # Russian
        ru_commands = build_bot_commands(
            command_names, lang="ru", translator=mock_translator
        )

        # Spanish
        es_commands = build_bot_commands(
            command_names, lang="es", translator=mock_translator
        )

        assert len(en_commands) == 2
        assert len(ru_commands) == 2
        assert len(es_commands) == 2

        # Check that descriptions are different for different languages
        en_descriptions = [cmd.description for cmd in en_commands]
        ru_descriptions = [cmd.description for cmd in ru_commands]
        es_descriptions = [cmd.description for cmd in es_commands]

        assert en_descriptions != ru_descriptions
        assert en_descriptions != es_descriptions
        assert ru_descriptions != es_descriptions

    def test_build_commands_with_missing_translations(self, noop_translator):
        """Test building commands when translations are missing."""
        command_names = ["start", "help", "profile"]

        commands = build_bot_commands(
            command_names, lang="en", translator=noop_translator
        )

        assert len(commands) == 3

        # Should fall back to Title Case
        descriptions = [cmd.description for cmd in commands]
        assert "Start" in descriptions
        assert "Help" in descriptions
        assert "Profile" in descriptions

    def test_build_commands_empty_list(self):
        """Test building commands with empty list."""
        commands = build_bot_commands([], lang="en")
        assert len(commands) == 0

    def test_build_commands_invalid_names(self):
        """Test building commands with invalid names."""
        invalid_names = ["", "123", "!!!", "   "]

        commands = build_bot_commands(invalid_names, lang="en")

        # Should handle invalid names gracefully
        assert len(commands) == 4
        assert all(isinstance(cmd, BotCommand) for cmd in commands)

    def test_build_commands_description_length_limit(self):
        """Test that descriptions respect Telegram's length limit."""

        # Create a translator that returns very long descriptions
        def long_translator(key: str, *, locale: str) -> str:
            return "A" * 300  # Much longer than 256 character limit

        command_names = ["start"]

        commands = build_bot_commands(
            command_names, lang="en", translator=long_translator
        )

        assert len(commands) == 1
        assert len(commands[0].description) <= 256

    def test_build_commands_command_name_length_limit(self):
        """Test that command names respect Telegram's length limit."""
        # Create a very long command name
        long_name = "a" * 50  # Longer than 32 character limit

        commands = build_bot_commands([long_name], lang="en")

        assert len(commands) == 1
        assert len(commands[0].command) <= 32

    def test_build_commands_translator_exception(self):
        """Test building commands when translator raises exception."""

        def failing_translator(key: str, *, locale: str) -> str:
            raise Exception("Translator error")

        command_names = ["start", "help"]

        commands = build_bot_commands(
            command_names, lang="en", translator=failing_translator
        )

        # Should fall back to Title Case when translator fails
        assert len(commands) == 2
        descriptions = [cmd.description for cmd in commands]
        assert "Start" in descriptions
        assert "Help" in descriptions

    def test_build_commands_unicode_support(self, mock_translator):
        """Test building commands with Unicode characters."""
        command_names = ["start", "help"]

        commands = build_bot_commands(
            command_names,
            lang="ru",  # Russian has Unicode characters
            translator=mock_translator,
        )

        assert len(commands) == 2

        # Check that Unicode descriptions are handled correctly
        descriptions = [cmd.description for cmd in commands]
        assert any("Запустить" in desc for desc in descriptions)
        assert any("справку" in desc for desc in descriptions)

    @pytest.mark.parametrize("lang", ["en", "ru", "es", "fr", "de"])
    def test_build_commands_different_languages(self, mock_translator, lang):
        """Test building commands for different languages."""
        command_names = ["start", "help"]

        commands = build_bot_commands(
            command_names, lang=lang, translator=mock_translator
        )

        assert len(commands) == 2
        assert all(isinstance(cmd, BotCommand) for cmd in commands)

    def test_build_commands_performance(self, mock_translator):
        """Test performance of command building."""
        import time

        command_names = ["start", "help", "profile", "settings", "admin"]

        # Warm up
        for _ in range(10):
            build_bot_commands(command_names, lang="en", translator=mock_translator)

        # Benchmark
        start_time = time.time()
        iterations = 1000

        for _ in range(iterations):
            build_bot_commands(command_names, lang="en", translator=mock_translator)

        end_time = time.time()
        duration = end_time - start_time

        # Should be fast (less than 1 second for 1000 iterations)
        assert duration < 1.0

        # Average time per build should be reasonable
        avg_time = duration / iterations
        assert avg_time < 0.001  # Less than 1ms per build
