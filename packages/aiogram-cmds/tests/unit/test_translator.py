"""
Tests for translator adapter: singular, plural, and explicit locale switching.
"""

from unittest.mock import Mock

from aiogram_cmds.translator import build_translator_from_i18n, noop_translator


def create_mock_i18n(gettext_return=None, ngettext_return=None):
    """Create a properly mocked aiogram I18n instance."""
    mock_i18n = Mock()
    mock_i18n.gettext.return_value = gettext_return
    mock_i18n.ngettext.return_value = ngettext_return

    # Mock with_locale context manager
    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_context)
    mock_context.__exit__ = Mock(return_value=None)
    mock_i18n.with_locale.return_value = mock_context

    return mock_i18n


class DummyLocaleCtx:
    def __init__(self, set_locale):
        self._set_locale = set_locale

    def __enter__(self):
        self._set_locale(True)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._set_locale(False)


class DummyI18n:
    """Minimal stub emulating aiogram I18n surface used by adapter."""

    def __init__(self, translations):
        self._translations = translations  # {(locale, key): value}
        self._current_locale = None

    def with_locale(self, locale):
        def set_locale(active):
            self._current_locale = locale if active else None

        return DummyLocaleCtx(set_locale)

    def _get_locale(self):
        # Used by adapter when locale is not explicitly provided
        return self._current_locale or "en"

    def gettext(self, key):
        loc = self._get_locale()
        return self._translations.get((loc, key), key)

    def ngettext(self, singular, plural, n):
        loc = self._get_locale()
        # Use basic English-like rule: n == 1 -> singular, else plural
        key = singular if n == 1 else plural
        return self._translations.get((loc, key), key)


def test_noop_translator_always_none():
    assert noop_translator("any", locale="en") is None
    assert noop_translator("any", locale=None) is None
    assert noop_translator("one", plural="many", count=2) is None


def test_singular_translation_with_explicit_locale():
    i18n = DummyI18n({("ru", "hello"): "привет"})
    t = build_translator_from_i18n(i18n)

    assert t("hello", locale="ru") == "привет"
    # Missing -> None
    assert t("missing", locale="ru") is None


def test_plural_translation_with_explicit_locale():
    i18n = DummyI18n(
        {
            ("en", "{n} file"): "1 file",
            ("en", "{n} files"): "{n} files",
            ("ru", "{n} file"): "1 файл",
            ("ru", "{n} files"): "{n} файла",
        }
    )
    t = build_translator_from_i18n(i18n)

    assert t("{n} file", plural="{n} files", count=1, locale="en") == "1 file"
    assert t("{n} file", plural="{n} files", count=3, locale="en") == "{n} files"
    assert t("{n} file", plural="{n} files", count=1, locale="ru") == "1 файл"
    assert t("{n} file", plural="{n} files", count=3, locale="ru") == "{n} файла"


def test_context_locale_resolution_without_explicit_locale():
    i18n = DummyI18n({("es", "hi"): "hola"})
    t = build_translator_from_i18n(i18n)

    # No locale set in context -> fallback to default in DummyI18n ("en"), expect None
    assert t("hi") is None

    # Use with_locale manually to emulate middleware context
    with i18n.with_locale("es"):
        assert t("hi") == "hola"


class TestTranslatorProtocol:
    """Test the Translator protocol."""

    def test_translator_protocol_interface(self):
        """Test that Translator protocol defines the correct interface."""
        # This test ensures the protocol is properly defined
        # We can't directly test protocols, but we can verify the interface

        def mock_translator(key: str, *, locale: str) -> str | None:
            return f"translated_{key}_{locale}"

        # Should work with any callable matching the signature
        result = mock_translator("test.key", locale="en")
        assert result == "translated_test.key_en"


class TestBuildTranslatorFromI18n:
    """Test build_translator_from_i18n function."""

    def test_build_translator_success(self):
        """Test successful translation."""
        mock_i18n = create_mock_i18n(gettext_return="Hello World")

        translator = build_translator_from_i18n(mock_i18n)
        result = translator("greeting", locale="en")

        assert result == "Hello World"
        mock_i18n.with_locale.assert_called_once_with("en")
        mock_i18n.gettext.assert_called_once_with("greeting")

    def test_build_translator_returns_none_for_empty_value(self):
        """Test that empty translation returns None."""
        mock_i18n = create_mock_i18n(gettext_return="")

        translator = build_translator_from_i18n(mock_i18n)
        result = translator("empty.key", locale="en")

        assert result is None
        mock_i18n.with_locale.assert_called_once_with("en")
        mock_i18n.gettext.assert_called_once_with("empty.key")

    def test_build_translator_returns_none_when_key_equals_value(self):
        """Test that when key equals value, returns None."""
        mock_i18n = create_mock_i18n(gettext_return="missing.key")

        translator = build_translator_from_i18n(mock_i18n)
        result = translator("missing.key", locale="en")

        assert result is None
        mock_i18n.with_locale.assert_called_once_with("en")
        mock_i18n.gettext.assert_called_once_with("missing.key")

    def test_build_translator_handles_exception(self):
        """Test that exceptions in gettext are handled gracefully."""
        mock_i18n = create_mock_i18n()
        mock_i18n.gettext.side_effect = Exception("Translation error")

        translator = build_translator_from_i18n(mock_i18n)
        result = translator("error.key", locale="en")

        assert result is None
        mock_i18n.with_locale.assert_called_once_with("en")
        mock_i18n.gettext.assert_called_once_with("error.key")

    def test_build_translator_handles_none_return(self):
        """Test that None return from gettext is handled."""
        mock_i18n = create_mock_i18n(gettext_return=None)

        translator = build_translator_from_i18n(mock_i18n)
        result = translator("none.key", locale="en")

        assert result is None
        mock_i18n.with_locale.assert_called_once_with("en")
        mock_i18n.gettext.assert_called_once_with("none.key")

    def test_build_translator_with_different_locales(self):
        """Test translator with different locales."""
        mock_i18n = create_mock_i18n()
        mock_i18n.gettext.side_effect = lambda key: f"{key}_translated"

        translator = build_translator_from_i18n(mock_i18n)

        result_en = translator("greeting", locale="en")
        result_ru = translator("greeting", locale="ru")
        result_es = translator("greeting", locale="es")

        assert result_en == "greeting_translated"
        assert result_ru == "greeting_translated"
        assert result_es == "greeting_translated"

        assert mock_i18n.with_locale.call_count == 3
        assert mock_i18n.gettext.call_count == 3

    def test_build_translator_preserves_original_key(self):
        """Test that the original key is preserved in translation calls."""
        mock_i18n = create_mock_i18n(gettext_return="Translated text")

        translator = build_translator_from_i18n(mock_i18n)
        result = translator("complex.key.with.dots", locale="en")

        assert result == "Translated text"
        mock_i18n.with_locale.assert_called_once_with("en")
        mock_i18n.gettext.assert_called_once_with("complex.key.with.dots")

    def test_build_translator_with_special_characters(self):
        """Test translator with special characters in key."""
        mock_i18n = create_mock_i18n(gettext_return="Special chars")

        translator = build_translator_from_i18n(mock_i18n)
        result = translator("key-with-special_chars.123", locale="en")

        assert result == "Special chars"
        mock_i18n.with_locale.assert_called_once_with("en")
        mock_i18n.gettext.assert_called_once_with("key-with-special_chars.123")


class TestNoopTranslator:
    """Test noop_translator function."""

    def test_noop_translator_always_returns_none(self):
        """Test that noop_translator always returns None."""
        result = noop_translator("any.key", locale="en")
        assert result is None

    def test_noop_translator_with_different_keys(self):
        """Test noop_translator with different keys."""
        keys = ["test.key", "another.key", "complex.key.with.dots"]
        locales = ["en", "ru", "es"]

        for key in keys:
            for locale in locales:
                result = noop_translator(key, locale=locale)
                assert result is None

    def test_noop_translator_with_special_characters(self):
        """Test noop_translator with special characters."""
        result = noop_translator("key-with-special_chars.123", locale="en")
        assert result is None

    def test_noop_translator_with_empty_key(self):
        """Test noop_translator with empty key."""
        result = noop_translator("", locale="en")
        assert result is None

    def test_noop_translator_with_empty_locale(self):
        """Test noop_translator with empty locale."""
        result = noop_translator("test.key", locale="")
        assert result is None


class TestTranslatorIntegration:
    """Integration tests for translator functionality."""

    def test_translator_consistency(self):
        """Test that translator functions are consistent in their interface."""
        mock_i18n = create_mock_i18n(gettext_return="Test translation")

        # Both should accept the same parameters
        built_translator = build_translator_from_i18n(mock_i18n)

        # Test both translators with same parameters
        result1 = built_translator("test.key", locale="en")
        result2 = noop_translator("test.key", locale="en")

        # Results should be different but both should be callable
        assert result1 == "Test translation"
        assert result2 is None

    def test_translator_error_handling_consistency(self):
        """Test that both translators handle errors gracefully."""
        mock_i18n = create_mock_i18n()
        mock_i18n.gettext.side_effect = Exception("Test error")

        built_translator = build_translator_from_i18n(mock_i18n)

        # Both should not raise exceptions
        result1 = built_translator("error.key", locale="en")
        result2 = noop_translator("error.key", locale="en")

        assert result1 is None
        assert result2 is None

    def test_translator_with_realistic_i18n_scenario(self):
        """Test translator with realistic i18n usage scenario."""
        mock_i18n = create_mock_i18n()

        def mock_gettext(key):
            translations = {
                "greeting": "Hello",
                "farewell": "Goodbye",
            }
            return translations.get(key, key)  # Return key if not found

        mock_i18n.gettext.side_effect = mock_gettext
        translator = build_translator_from_i18n(mock_i18n)

        # Test existing translations
        assert translator("greeting", locale="en") == "Hello"
        assert translator("farewell", locale="en") == "Goodbye"

        # Test missing translations (should return None when key equals value)
        assert translator("missing.key", locale="en") is None
