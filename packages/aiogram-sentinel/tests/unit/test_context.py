"""Unit tests for context extractor functions."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from aiogram_sentinel.context import (
    extract_callback_bucket,
    extract_chat_id,
    extract_event_type,
    extract_group_ids,
    extract_handler_bucket,
    extract_user_id,
)


@pytest.mark.unit
class TestExtractUserId:
    """Test extract_user_id function."""

    def test_extract_user_id_from_message(self) -> None:
        """Test extracting user ID from Message."""
        user = User(id=12345, is_bot=False, first_name="Test")
        chat = Chat(id=67890, type="private")
        message = Message(
            message_id=1,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text="test",
        )

        user_id = extract_user_id(message, {})
        assert user_id == 12345

    def test_extract_user_id_from_callback_query(self) -> None:
        """Test extracting user ID from CallbackQuery."""
        user = User(id=12345, is_bot=False, first_name="Test")
        callback = CallbackQuery(
            id="test_id",
            from_user=user,
            chat_instance="test_instance",
            data="test_data",
        )

        user_id = extract_user_id(callback, {})
        assert user_id == 12345

    def test_extract_user_id_from_user_attribute(self) -> None:
        """Test extracting user ID from event with user attribute."""
        user = User(id=12345, is_bot=False, first_name="Test")
        event = Mock()
        event.from_user = None
        event.user = user
        event.chat = None

        user_id = extract_user_id(event, {})
        assert user_id == 12345

    def test_extract_user_id_from_chat_fallback(self) -> None:
        """Test extracting user ID from chat as fallback for private chats."""
        chat = Chat(id=12345, type="private")  # Private chat ID equals user ID
        event = Mock()
        event.from_user = None
        event.user = None
        event.chat = chat

        user_id = extract_user_id(event, {})
        assert user_id == 12345

    def test_extract_user_id_none_when_no_user(self) -> None:
        """Test that None is returned when no user information is available."""
        event = Mock()
        event.from_user = None
        event.user = None
        event.chat = None

        user_id = extract_user_id(event, {})
        assert user_id is None

    def test_extract_user_id_none_for_group_chat(self) -> None:
        """Test that None is returned for group chats (chat ID != user ID)."""
        chat = Chat(id=67890, type="group")  # Group chat ID != user ID
        event = Mock()
        event.from_user = None
        event.user = None
        event.chat = chat

        user_id = extract_user_id(event, {})
        assert user_id is None

    def test_extract_user_id_none_for_negative_chat_id(self) -> None:
        """Test that None is returned for negative chat IDs."""
        chat = Chat(id=-12345, type="private")  # Negative chat ID
        event = Mock()
        event.from_user = None
        event.user = None
        event.chat = chat

        user_id = extract_user_id(event, {})
        assert user_id is None


@pytest.mark.unit
class TestExtractChatId:
    """Test extract_chat_id function."""

    def test_extract_chat_id_from_message(self) -> None:
        """Test extracting chat ID from Message."""
        user = User(id=12345, is_bot=False, first_name="Test")
        chat = Chat(id=67890, type="private")
        message = Message(
            message_id=1,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text="test",
        )

        chat_id = extract_chat_id(message, {})
        assert chat_id == 67890

    def test_extract_chat_id_from_callback_query(self) -> None:
        """Test extracting chat ID from CallbackQuery."""
        user = User(id=12345, is_bot=False, first_name="Test")
        chat = Chat(id=67890, type="private")
        callback = CallbackQuery(
            id="test_id",
            from_user=user,
            chat_instance="test_instance",
            data="test_data",
            chat=chat,
        )

        chat_id = extract_chat_id(callback, {})
        assert chat_id == 67890

    def test_extract_chat_id_from_message_attribute(self) -> None:
        """Test extracting chat ID from event with message attribute."""
        chat = Chat(id=67890, type="private")
        message = Mock()
        message.chat = chat

        event = Mock()
        event.chat = None
        event.message = message

        chat_id = extract_chat_id(event, {})
        assert chat_id == 67890

    def test_extract_chat_id_none_when_no_chat(self) -> None:
        """Test that None is returned when no chat information is available."""
        event = Mock()
        event.chat = None
        event.message = None

        chat_id = extract_chat_id(event, {})
        assert chat_id is None


@pytest.mark.unit
class TestExtractGroupIds:
    """Test extract_group_ids function."""

    def test_extract_group_ids_both_available(self) -> None:
        """Test extracting both user and chat IDs when both are available."""
        user = User(id=12345, is_bot=False, first_name="Test")
        chat = Chat(id=67890, type="private")
        message = Message(
            message_id=1,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text="test",
        )

        user_id, chat_id = extract_group_ids(message, {})
        assert user_id == 12345
        assert chat_id == 67890

    def test_extract_group_ids_only_user(self) -> None:
        """Test extracting group IDs when only user is available."""
        user = User(id=12345, is_bot=False, first_name="Test")
        event = Mock()
        event.from_user = user
        event.user = None
        event.chat = None
        event.message = None  # Explicitly set to None

        user_id, chat_id = extract_group_ids(event, {})
        assert user_id == 12345
        assert chat_id is None

    def test_extract_group_ids_only_chat(self) -> None:
        """Test extracting group IDs when only chat is available."""
        chat = Chat(id=67890, type="private")
        event = Mock()
        event.from_user = None
        event.user = None
        event.chat = chat
        event.message = None  # Explicitly set to None

        user_id, chat_id = extract_group_ids(event, {})
        assert user_id == 67890  # For private chats, user_id == chat_id
        assert chat_id == 67890

    def test_extract_group_ids_neither_available(self) -> None:
        """Test extracting group IDs when neither is available."""
        event = Mock()
        event.from_user = None
        event.user = None
        event.chat = None
        event.message = None  # Explicitly set to None

        user_id, chat_id = extract_group_ids(event, {})
        assert user_id is None
        assert chat_id is None


@pytest.mark.unit
class TestExtractEventType:
    """Test extract_event_type function."""

    def test_extract_event_type_message(self) -> None:
        """Test extracting event type from Message."""
        user = User(id=12345, is_bot=False, first_name="Test")
        chat = Chat(id=67890, type="private")
        message = Message(
            message_id=1,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text="test",
        )

        event_type = extract_event_type(message, {})
        assert event_type == "message"

    def test_extract_event_type_callback_query(self) -> None:
        """Test extracting event type from CallbackQuery."""
        user = User(id=12345, is_bot=False, first_name="Test")
        callback = CallbackQuery(
            id="test_id",
            from_user=user,
            chat_instance="test_instance",
            data="test_data",
        )

        event_type = extract_event_type(callback, {})
        assert event_type == "callback"

    def test_extract_event_type_custom_event(self) -> None:
        """Test extracting event type from custom event."""
        event = Mock()
        event.__class__.__name__ = "CustomEvent"

        event_type = extract_event_type(event, {})
        assert event_type == "customevent"

    def test_extract_event_type_mapped_names(self) -> None:
        """Test that specific event types are mapped to readable names."""
        # Test a few mapped event types
        test_cases = [
            ("InlineQuery", "inline"),
            ("ChatMemberUpdated", "chat_member"),
            ("MyCommand", "command"),
            ("ForumTopicCreated", "forum_topic"),
            ("VideoChatStarted", "video_chat"),
            ("BusinessConnection", "business"),
        ]

        for class_name, expected_type in test_cases:
            event = Mock()
            event.__class__.__name__ = class_name

            event_type = extract_event_type(event, {})
            assert event_type == expected_type


@pytest.mark.unit
class TestExtractHandlerBucket:
    """Test extract_handler_bucket function."""

    def test_extract_handler_bucket_from_data(self) -> None:
        """Test extracting handler bucket from data."""
        handler = Mock()
        handler.__name__ = "test_handler"

        event = Mock()
        data = {"handler": handler}

        bucket = extract_handler_bucket(event, data)
        assert bucket == "test_handler"

    def test_extract_handler_bucket_from_event(self) -> None:
        """Test extracting handler bucket from event."""
        handler = Mock()
        handler.__name__ = "test_handler"

        event = Mock()
        event.handler = handler

        bucket = extract_handler_bucket(event, {})
        assert bucket == "test_handler"

    def test_extract_handler_bucket_none_when_no_handler(self) -> None:
        """Test that None is returned when no handler is available."""
        event = Mock()
        event.handler = None

        bucket = extract_handler_bucket(event, {})
        assert bucket is None

    def test_extract_handler_bucket_none_when_handler_no_name(self) -> None:
        """Test that None is returned when handler has no __name__ attribute."""
        handler = Mock(spec=[])  # Mock without __name__

        event = Mock()
        event.handler = handler

        bucket = extract_handler_bucket(event, {})
        assert bucket is None


@pytest.mark.unit
class TestExtractCallbackBucket:
    """Test extract_callback_bucket function."""

    def test_extract_callback_bucket_with_colon(self) -> None:
        """Test extracting callback bucket with colon separator."""
        event = Mock()
        event.data = "action:param1:param2"

        bucket = extract_callback_bucket(event, {})
        assert bucket == "action"

    def test_extract_callback_bucket_with_underscore(self) -> None:
        """Test extracting callback bucket with underscore separator."""
        event = Mock()
        event.data = "action_param1_param2"

        bucket = extract_callback_bucket(event, {})
        assert bucket == "action"

    def test_extract_callback_bucket_no_separator(self) -> None:
        """Test extracting callback bucket without separator."""
        event = Mock()
        event.data = "action"

        bucket = extract_callback_bucket(event, {})
        assert bucket == "action"

    def test_extract_callback_bucket_none_when_no_data(self) -> None:
        """Test that None is returned when no data is available."""
        event = Mock()
        event.data = None

        bucket = extract_callback_bucket(event, {})
        assert bucket is None

    def test_extract_callback_bucket_none_when_no_data_attribute(self) -> None:
        """Test that None is returned when event has no data attribute."""
        event = Mock(spec=[])  # Mock without data attribute

        bucket = extract_callback_bucket(event, {})
        assert bucket is None

    def test_extract_callback_bucket_empty_data(self) -> None:
        """Test extracting callback bucket with empty data."""
        event = Mock()
        event.data = ""

        bucket = extract_callback_bucket(event, {})
        assert bucket == ""

    def test_extract_callback_bucket_complex_data(self) -> None:
        """Test extracting callback bucket with complex data."""
        test_cases = [
            ("user:123:action:edit", "user"),
            ("settings_theme_dark", "settings"),
            ("simple_action", "simple_action"),  # Single underscore, no split
            ("", ""),
        ]

        for data, expected in test_cases:
            event = Mock()
            event.data = data

            bucket = extract_callback_bucket(event, {})
            assert bucket == expected


@pytest.mark.unit
class TestContextExtractorsEdgeCases:
    """Test context extractors with edge cases."""

    def test_extract_user_id_with_none_attributes(self) -> None:
        """Test extract_user_id with None attributes."""
        event = Mock()
        event.from_user = None
        event.user = None
        event.chat = None

        user_id = extract_user_id(event, {})
        assert user_id is None

    def test_extract_chat_id_with_none_attributes(self) -> None:
        """Test extract_chat_id with None attributes."""
        event = Mock()
        event.chat = None
        event.message = None

        chat_id = extract_chat_id(event, {})
        assert chat_id is None

    def test_extract_event_type_with_missing_class_name(self) -> None:
        """Test extract_event_type with missing class name."""

        # Create a mock that doesn't have __name__ attribute
        class MockEvent:
            pass

        event = MockEvent()

        # This should not raise an exception
        event_type = extract_event_type(event, {})  # type: ignore[arg-type]
        # Should fall back to some default or handle gracefully
        assert isinstance(event_type, str)

    def test_extract_handler_bucket_with_invalid_handler(self) -> None:
        """Test extract_handler_bucket with invalid handler."""
        handler = "not_a_handler"  # String instead of callable

        event = Mock()
        data = {"handler": handler}

        bucket = extract_handler_bucket(event, data)
        assert bucket is None

    def test_extract_callback_bucket_with_non_string_data(self) -> None:
        """Test extract_callback_bucket with non-string data."""
        event = Mock()
        event.data = 12345  # Integer instead of string

        bucket = extract_callback_bucket(event, {})
        assert bucket == "12345"  # Should convert to string

    def test_all_extractors_with_empty_data(self) -> None:
        """Test all extractors with empty data dictionary."""
        user = User(id=12345, is_bot=False, first_name="Test")
        chat = Chat(id=67890, type="private")
        message = Message(
            message_id=1,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text="test",
        )

        # All extractors should work with empty data
        user_id = extract_user_id(message, {})
        chat_id = extract_chat_id(message, {})
        group_ids = extract_group_ids(message, {})
        event_type = extract_event_type(message, {})
        handler_bucket = extract_handler_bucket(message, {})
        callback_bucket = extract_callback_bucket(message, {})

        assert user_id == 12345
        assert chat_id == 67890
        assert group_ids == (12345, 67890)
        assert event_type == "message"
        assert handler_bucket is None  # No handler in data
        assert callback_bucket is None  # No callback data
