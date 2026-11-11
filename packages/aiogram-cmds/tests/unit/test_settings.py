"""
Unit tests for the settings module.
"""

import pytest
from pydantic import ValidationError

from aiogram_cmds.settings import CmdsSettings, load_settings


class TestCmdsSettings:
    """Test CmdsSettings class."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = CmdsSettings()

        assert settings.languages == ("en",)
        assert settings.fallback_language == "en"
        assert settings.i18n_key_prefix == "cmd"
        assert settings.profile == "default"
        assert settings.menu_button == "commands"

    def test_custom_settings(self):
        """Test custom settings values."""
        settings = CmdsSettings(
            languages=["en", "ru", "es"],
            fallback_language="ru",
            i18n_key_prefix="bot",
            profile="custom",
            menu_button="default",
        )

        assert settings.languages == ("en", "ru", "es")
        assert settings.fallback_language == "ru"
        assert settings.i18n_key_prefix == "bot"
        assert settings.profile == "custom"
        assert settings.menu_button == "default"

    def test_languages_validation_empty_list(self):
        """Test that empty languages list is handled."""
        settings = CmdsSettings(languages=[])

        # Should default to ["en"]
        assert settings.languages == ("en",)

    def test_languages_validation_none(self):
        """Test that None languages is handled."""
        settings = CmdsSettings(languages=None)

        # Should default to ["en"]
        assert settings.languages == ("en",)

    def test_languages_validation_single_string(self):
        """Test that single string language is handled."""
        settings = CmdsSettings(languages="en")

        # Should be converted to tuple
        assert settings.languages == ("en",)

    def test_settings_immutability(self):
        """Test that settings are immutable after creation."""
        settings = CmdsSettings(languages=["en", "ru"])

        # Should not be able to modify fields directly
        with pytest.raises(ValidationError):
            settings.languages = ["es"]

    def test_settings_equality(self):
        """Test settings equality."""
        settings1 = CmdsSettings(languages=["en", "ru"])
        settings2 = CmdsSettings(languages=["en", "ru"])
        settings3 = CmdsSettings(languages=["en", "es"])

        assert settings1 == settings2
        assert settings1 != settings3

    def test_settings_hash(self):
        """Test settings hashing."""
        settings1 = CmdsSettings(languages=["en", "ru"])
        settings2 = CmdsSettings(languages=["en", "ru"])
        settings3 = CmdsSettings(languages=["en", "es"])

        assert hash(settings1) == hash(settings2)
        assert hash(settings1) != hash(settings3)

    def test_settings_repr(self):
        """Test settings string representation."""
        settings = CmdsSettings(
            languages=["en", "ru"], fallback_language="en", i18n_key_prefix="cmd"
        )
        repr_str = repr(settings)

        assert "CmdsSettings" in repr_str
        assert "languages=" in repr_str
        assert "fallback_language=" in repr_str
        assert "i18n_key_prefix=" in repr_str

    def test_settings_serialization(self):
        """Test settings serialization."""
        settings = CmdsSettings(
            languages=["en", "ru", "es"],
            fallback_language="en",
            i18n_key_prefix="bot",
            profile="custom",
            menu_button="default",
        )

        # Should be serializable to dict
        settings_dict = settings.model_dump()

        assert isinstance(settings_dict, dict)
        assert settings_dict["languages"] == ("en", "ru", "es")
        assert settings_dict["fallback_language"] == "en"
        assert settings_dict["i18n_key_prefix"] == "bot"
        assert settings_dict["profile"] == "custom"
        assert settings_dict["menu_button"] == "default"

    def test_settings_deserialization(self):
        """Test settings deserialization."""
        settings_dict = {
            "languages": ["en", "ru", "es"],
            "fallback_language": "en",
            "i18n_key_prefix": "bot",
            "profile": "custom",
            "menu_button": "default",
        }

        settings = CmdsSettings.model_validate(settings_dict)

        assert settings.languages == ("en", "ru", "es")
        assert settings.fallback_language == "en"
        assert settings.i18n_key_prefix == "bot"
        assert settings.profile == "custom"
        assert settings.menu_button == "default"

    def test_settings_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        settings_dict = {
            "languages": ["en", "ru"],
            "fallback_language": "en",
            "i18n_key_prefix": "cmd",
            "profile": "default",
            "menu_button": "commands",
            "extra_field": "should_be_ignored",
            "another_extra": 123,
        }

        settings = CmdsSettings.model_validate(settings_dict)

        # Should not have extra fields
        assert not hasattr(settings, "extra_field")
        assert not hasattr(settings, "another_extra")

        # Should have all expected fields
        assert settings.languages == ("en", "ru")
        assert settings.fallback_language == "en"
        assert settings.i18n_key_prefix == "cmd"
        assert settings.profile == "default"
        assert settings.menu_button == "commands"


class TestLoadSettings:
    """Test load_settings function."""

    def test_load_settings_default(self):
        """Test loading settings with defaults."""
        settings = load_settings()

        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en",)
        assert settings.fallback_language == "en"
        assert settings.i18n_key_prefix == "cmd"
        assert settings.profile == "default"
        assert settings.menu_button == "commands"

    def test_load_settings_nonexistent_file(self, tmp_path):
        """Test loading settings from nonexistent file."""
        nonexistent_file = tmp_path / "nonexistent.toml"

        settings = load_settings(nonexistent_file)

        # Should return default settings
        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en",)
        assert settings.fallback_language == "en"

    def test_load_settings_valid_file(self, temp_config_file):
        """Test loading settings from valid file."""
        settings = load_settings(temp_config_file)

        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en", "ru", "es")
        assert settings.fallback_language == "en"
        assert settings.i18n_key_prefix == "cmd"
        assert settings.profile == "default"
        assert settings.menu_button == "commands"

    def test_load_settings_invalid_toml(self, tmp_path):
        """Test loading settings from invalid TOML file."""
        invalid_file = tmp_path / "invalid.toml"
        invalid_file.write_text("invalid toml content {")

        settings = load_settings(invalid_file)

        # Should return default settings on error
        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en",)
        assert settings.fallback_language == "en"

    def test_load_settings_missing_section(self, tmp_path):
        """Test loading settings from file without aiogram_cmds section."""
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text("""
[other_section]
key = "value"
""")

        settings = load_settings(config_file)

        # Should return default settings
        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en",)
        assert settings.fallback_language == "en"

    def test_load_settings_partial_config(self, tmp_path):
        """Test loading settings with partial configuration."""
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text("""
[tool.aiogram_cmds]
languages = ["en", "ru"]
fallback_language = "ru"
# Other fields should use defaults
""")

        settings = load_settings(config_file)

        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en", "ru")
        assert settings.fallback_language == "ru"
        assert settings.i18n_key_prefix == "cmd"  # Default
        assert settings.profile == "default"  # Default
        assert settings.menu_button == "commands"  # Default

    def test_load_settings_invalid_values(self, tmp_path):
        """Test loading settings with invalid values."""
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text("""
[tool.aiogram_cmds]
languages = []  # Empty list should be handled
fallback_language = "invalid"  # Not in languages list
menu_button = "invalid_mode"  # Invalid menu button mode
""")

        settings = load_settings(config_file)

        # Should handle invalid values gracefully
        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en",)  # Should default
        assert settings.fallback_language == "invalid"  # Should keep as is
        assert settings.menu_button == "invalid_mode"  # Should keep as is

    def test_load_settings_custom_path(self, tmp_path):
        """Test loading settings with custom path."""
        config_file = tmp_path / "custom.toml"
        config_file.write_text("""
[tool.aiogram_cmds]
languages = ["en", "es"]
fallback_language = "es"
i18n_key_prefix = "custom"
""")

        settings = load_settings(config_file)

        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en", "es")
        assert settings.fallback_language == "es"
        assert settings.i18n_key_prefix == "custom"

    def test_load_settings_logging(self, tmp_path, caplog):
        """Test that load_settings logs warnings on errors."""
        import logging

        # Create invalid TOML file
        invalid_file = tmp_path / "invalid.toml"
        invalid_file.write_text("invalid toml content {")

        with caplog.at_level(logging.WARNING):
            settings = load_settings(invalid_file)

        # Should log warning
        assert "failed to load settings" in caplog.text.lower()

        # Should still return default settings
        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en",)

    def test_load_settings_no_logging_on_success(self, temp_config_file, caplog):
        """Test that load_settings doesn't log on success."""
        import logging

        with caplog.at_level(logging.INFO):
            settings = load_settings(temp_config_file)

        # Should not log anything
        assert len(caplog.records) == 0

        # Should return loaded settings
        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en", "ru", "es")

    def test_load_settings_encoding_handling(self, tmp_path):
        """Test that load_settings handles different encodings."""
        config_file = tmp_path / "pyproject.toml"

        # Write with UTF-8 encoding (default)
        config_file.write_text(
            """
[tool.aiogram_cmds]
languages = ["en", "ru"]
fallback_language = "en"
""",
            encoding="utf-8",
        )

        settings = load_settings(config_file)

        assert isinstance(settings, CmdsSettings)
        assert settings.languages == ("en", "ru")
        assert settings.fallback_language == "en"

    def test_load_settings_performance(self, temp_config_file):
        """Test load_settings performance."""
        import time

        # Warm up
        for _ in range(10):
            load_settings(temp_config_file)

        # Benchmark
        start_time = time.time()
        iterations = 1000

        for _ in range(iterations):
            load_settings(temp_config_file)

        end_time = time.time()
        duration = end_time - start_time

        # Should be fast
        assert duration < 1.0  # Less than 1 second for 1000 iterations

        # Average time per load should be reasonable
        avg_time = duration / iterations
        assert avg_time < 0.001  # Less than 1ms per load
