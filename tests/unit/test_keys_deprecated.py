"""Unit tests for backward compatibility of deprecated key functions."""

import warnings
from unittest.mock import patch

import pytest

from aiogram_sentinel.utils.keys import debounce_key, rate_key


@pytest.mark.unit
class TestDeprecatedKeyFunctions:
    """Test deprecated key functions for backward compatibility."""

    def test_rate_key_deprecation_warning(self) -> None:
        """Test that rate_key emits deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Call the deprecated function
            rate_key(123, "test_handler")

            # Check that deprecation warning was emitted
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "rate_key() is deprecated" in str(w[0].message)

    def test_debounce_key_deprecation_warning(self) -> None:
        """Test that debounce_key emits deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Call the deprecated function
            debounce_key(123, "test_handler")

            # Check that deprecation warning was emitted
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "debounce_key() is deprecated" in str(w[0].message)

    def test_rate_key_logging_warning(self) -> None:
        """Test that rate_key logs warning."""
        with patch("aiogram_sentinel.utils.keys.logger") as mock_logger:
            # Call the deprecated function
            rate_key(123, "test_handler")

            # Check that warning was logged
            mock_logger.warning.assert_called_once()
            warning_message = mock_logger.warning.call_args[0][0]
            assert "rate_key() is deprecated" in warning_message

    def test_debounce_key_logging_warning(self) -> None:
        """Test that debounce_key logs warning."""
        with patch("aiogram_sentinel.utils.keys.logger") as mock_logger:
            # Call the deprecated function
            debounce_key(123, "test_handler")

            # Check that warning was logged
            mock_logger.warning.assert_called_once()
            warning_message = mock_logger.warning.call_args[0][0]
            assert "debounce_key() is deprecated" in warning_message

    def test_rate_key_output_unchanged(self) -> None:
        """Test that rate_key produces same output as before."""
        # Test basic usage
        key1 = rate_key(123, "test_handler")
        expected1 = "123:test_handler"
        assert key1 == expected1

        # Test with additional kwargs
        key2 = rate_key(123, "test_handler", chat_id=456, message_id=789)
        expected2 = "123:test_handler:chat_id:456:message_id:789"
        assert key2 == expected2

        # Test with multiple kwargs (should be sorted)
        key3 = rate_key(123, "test_handler", z_param=999, a_param=111)
        expected3 = "123:test_handler:a_param:111:z_param:999"
        assert key3 == expected3

    def test_debounce_key_output_unchanged(self) -> None:
        """Test that debounce_key produces same output as before."""
        # Test basic usage
        key1 = debounce_key(123, "test_handler")
        expected1 = "123:test_handler"
        assert key1 == expected1

        # Test with additional kwargs
        key2 = debounce_key(123, "test_handler", chat_id=456, message_id=789)
        expected2 = "123:test_handler:chat_id:456:message_id:789"
        assert key2 == expected2

        # Test with multiple kwargs (should be sorted)
        key3 = debounce_key(123, "test_handler", z_param=999, a_param=111)
        expected3 = "123:test_handler:a_param:111:z_param:999"
        assert key3 == expected3

    def test_rate_key_with_various_user_ids(self) -> None:
        """Test rate_key with various user ID types."""
        test_cases = [
            (123, "123"),
            (0, "0"),
            (-123, "-123"),
            (999999999, "999999999"),
        ]

        for user_id, expected_str in test_cases:
            key = rate_key(user_id, "test_handler")
            expected = f"{expected_str}:test_handler"
            assert key == expected

    def test_debounce_key_with_various_user_ids(self) -> None:
        """Test debounce_key with various user ID types."""
        test_cases = [
            (123, "123"),
            (0, "0"),
            (-123, "-123"),
            (999999999, "999999999"),
        ]

        for user_id, expected_str in test_cases:
            key = debounce_key(user_id, "test_handler")
            expected = f"{expected_str}:test_handler"
            assert key == expected

    def test_rate_key_with_various_handler_names(self) -> None:
        """Test rate_key with various handler names."""
        test_cases = [
            "simple_handler",
            "handler_with_underscores",
            "HandlerWithCamelCase",
            "handler123",
            "handler-with-dashes",
            "handler.with.dots",
            "handler with spaces",
            "handler_with_unicode_测试",
        ]

        for handler_name in test_cases:
            key = rate_key(123, handler_name)
            expected = f"123:{handler_name}"
            assert key == expected

    def test_debounce_key_with_various_handler_names(self) -> None:
        """Test debounce_key with various handler names."""
        test_cases = [
            "simple_handler",
            "handler_with_underscores",
            "HandlerWithCamelCase",
            "handler123",
            "handler-with-dashes",
            "handler.with.dots",
            "handler with spaces",
            "handler_with_unicode_测试",
        ]

        for handler_name in test_cases:
            key = debounce_key(123, handler_name)
            expected = f"123:{handler_name}"
            assert key == expected

    def test_rate_key_kwargs_sorting(self) -> None:
        """Test that rate_key sorts kwargs alphabetically."""
        key = rate_key(123, "test_handler", z_param=999, a_param=111, m_param=555)
        expected = "123:test_handler:a_param:111:m_param:555:z_param:999"
        assert key == expected

    def test_debounce_key_kwargs_sorting(self) -> None:
        """Test that debounce_key sorts kwargs alphabetically."""
        key = debounce_key(123, "test_handler", z_param=999, a_param=111, m_param=555)
        expected = "123:test_handler:a_param:111:m_param:555:z_param:999"
        assert key == expected

    def test_rate_key_kwargs_values_conversion(self) -> None:
        """Test that rate_key converts kwargs values to strings."""
        key = rate_key(
            123,
            "test_handler",
            int_param=456,
            float_param=789.0,
            bool_param=True,
            none_param=None,
        )
        expected = "123:test_handler:bool_param:True:float_param:789.0:int_param:456:none_param:None"
        assert key == expected

    def test_debounce_key_kwargs_values_conversion(self) -> None:
        """Test that debounce_key converts kwargs values to strings."""
        key = debounce_key(
            123,
            "test_handler",
            int_param=456,
            float_param=789.0,
            bool_param=True,
            none_param=None,
        )
        expected = "123:test_handler:bool_param:True:float_param:789.0:int_param:456:none_param:None"
        assert key == expected

    def test_rate_key_empty_kwargs(self) -> None:
        """Test rate_key with no additional kwargs."""
        key = rate_key(123, "test_handler")
        expected = "123:test_handler"
        assert key == expected

    def test_debounce_key_empty_kwargs(self) -> None:
        """Test debounce_key with no additional kwargs."""
        key = debounce_key(123, "test_handler")
        expected = "123:test_handler"
        assert key == expected

    def test_rate_key_complex_kwargs(self) -> None:
        """Test rate_key with complex kwargs values."""
        key = rate_key(
            123,
            "test_handler",
            complex_dict={"key": "value"},
            complex_list=[1, 2, 3],
            complex_tuple=(4, 5, 6),
        )

        # The exact format depends on how Python converts these to strings
        # We just verify it doesn't crash and produces a string
        assert isinstance(key, str)
        assert key.startswith("123:test_handler:")
        assert "complex_dict" in key
        assert "complex_list" in key
        assert "complex_tuple" in key

    def test_debounce_key_complex_kwargs(self) -> None:
        """Test debounce_key with complex kwargs values."""
        key = debounce_key(
            123,
            "test_handler",
            complex_dict={"key": "value"},
            complex_list=[1, 2, 3],
            complex_tuple=(4, 5, 6),
        )

        # The exact format depends on how Python converts these to strings
        # We just verify it doesn't crash and produces a string
        assert isinstance(key, str)
        assert key.startswith("123:test_handler:")
        assert "complex_dict" in key
        assert "complex_list" in key
        assert "complex_tuple" in key

    def test_deprecated_functions_consistency(self) -> None:
        """Test that both deprecated functions produce consistent output."""
        # Same inputs should produce same format
        rate_key_output = rate_key(123, "test_handler", chat_id=456)
        debounce_key_output = debounce_key(123, "test_handler", chat_id=456)

        # Both should have same format: user_id:handler_name:sorted_kwargs
        assert rate_key_output == debounce_key_output
        assert rate_key_output == "123:test_handler:chat_id:456"

    def test_deprecated_functions_deterministic(self) -> None:
        """Test that deprecated functions are deterministic."""
        # Multiple calls with same inputs should produce identical output
        key1 = rate_key(123, "test_handler", a=1, b=2)
        key2 = rate_key(123, "test_handler", a=1, b=2)
        key3 = rate_key(123, "test_handler", a=1, b=2)

        assert key1 == key2 == key3

        # Same for debounce_key
        key4 = debounce_key(123, "test_handler", a=1, b=2)
        key5 = debounce_key(123, "test_handler", a=1, b=2)
        key6 = debounce_key(123, "test_handler", a=1, b=2)

        assert key4 == key5 == key6
