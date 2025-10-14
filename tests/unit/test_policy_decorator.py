"""Unit tests for policy decorator."""

import pytest

from aiogram_sentinel.policy import policy


@pytest.mark.unit
class TestPolicyDecorator:
    """Test @policy decorator functionality."""

    def test_single_policy_attachment(self) -> None:
        """Test attaching single policy to handler."""

        @policy("user_throttle")
        async def handler():
            return "test"

        assert hasattr(handler, "__sentinel_policies__")  # type: ignore[attr-defined]
        assert handler.__sentinel_policies__ == ("user_throttle",)  # type: ignore[attr-defined]

    def test_multiple_policies_attachment(self) -> None:
        """Test attaching multiple policies to handler."""

        @policy("user_throttle", "user_debounce")
        async def handler():
            return "test"

        assert hasattr(handler, "__sentinel_policies__")  # type: ignore[attr-defined]
        assert handler.__sentinel_policies__ == ("user_throttle", "user_debounce")  # type: ignore[attr-defined]

    def test_multiple_policies_preserves_order(self) -> None:
        """Test that multiple policies preserve order."""

        @policy("first", "second", "third")
        async def handler():
            return "test"

        assert handler.__sentinel_policies__ == ("first", "second", "third")  # type: ignore[attr-defined]

    def test_decorator_works_with_sync_function(self) -> None:
        """Test that decorator works with sync functions."""

        @policy("test_policy")
        def sync_handler():
            return "test"

        assert hasattr(sync_handler, "__sentinel_policies__")  # type: ignore[attr-defined]
        assert sync_handler.__sentinel_policies__ == ("test_policy",)  # type: ignore[attr-defined]

    def test_decorator_works_with_class_method(self) -> None:
        """Test that decorator works with class methods."""

        class TestClass:
            @policy("class_policy")
            async def method(self):
                return "test"

        instance = TestClass()
        assert hasattr(instance.method, "__sentinel_policies__")  # type: ignore[attr-defined]
        assert instance.method.__sentinel_policies__ == ("class_policy",)  # type: ignore[attr-defined]

    def test_no_policy_names_error(self) -> None:
        """Test that providing no policy names raises error."""
        with pytest.raises(
            ValueError, match="At least one policy name must be provided"
        ):

            @policy()
            async def handler():  # type: ignore[unused-function]
                return "test"

    def test_empty_policy_name_allowed(self) -> None:
        """Test that empty policy name is allowed (validation happens later)."""

        @policy("")
        async def handler():
            return "test"

        assert handler.__sentinel_policies__ == ("",)  # type: ignore[attr-defined]

    def test_decorator_preserves_function_metadata(self) -> None:
        """Test that decorator preserves function metadata."""

        @policy("test_policy")
        async def handler_with_docstring():
            """This is a test handler."""
            return "test"

        assert handler_with_docstring.__name__ == "handler_with_docstring"
        assert handler_with_docstring.__doc__ == "This is a test handler."
        assert handler_with_docstring.__sentinel_policies__ == ("test_policy",)  # type: ignore[attr-defined]
