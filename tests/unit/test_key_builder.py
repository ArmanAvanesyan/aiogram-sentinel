"""Unit tests for KeyBuilder and related components."""

import pytest

from aiogram_sentinel.scopes import KeyBuilder, KeyParts, Scope


@pytest.mark.unit
class TestScope:
    """Test Scope enum."""

    def test_scope_values(self) -> None:
        """Test that Scope enum has expected values."""
        assert Scope.USER.value == "user"
        assert Scope.CHAT.value == "chat"
        assert Scope.GROUP.value == "group"
        assert Scope.GLOBAL.value == "global"

    def test_scope_names(self) -> None:
        """Test that Scope enum has expected names."""
        assert Scope.USER.name == "USER"
        assert Scope.CHAT.name == "CHAT"
        assert Scope.GROUP.name == "GROUP"
        assert Scope.GLOBAL.name == "GLOBAL"


@pytest.mark.unit
class TestKeyParts:
    """Test KeyParts dataclass."""

    def test_key_parts_creation(self) -> None:
        """Test creating KeyParts with valid data."""
        parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123",))
        assert parts.namespace == "throttle"
        assert parts.scope == Scope.USER
        assert parts.identifiers == ("123",)

    def test_key_parts_empty_namespace(self) -> None:
        """Test that empty namespace raises ValueError."""
        with pytest.raises(ValueError, match="namespace cannot be empty"):
            KeyParts(namespace="", scope=Scope.USER, identifiers=("123",))

    def test_key_parts_empty_identifiers(self) -> None:
        """Test that empty identifiers raises ValueError."""
        with pytest.raises(ValueError, match="identifiers cannot be empty"):
            KeyParts(namespace="throttle", scope=Scope.USER, identifiers=())

    def test_key_parts_empty_identifier(self) -> None:
        """Test that empty identifier raises ValueError."""
        with pytest.raises(ValueError, match="identifier cannot be empty"):
            KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("",))

    def test_key_parts_separator_in_identifier(self) -> None:
        """Test that separator in identifier raises ValueError."""
        with pytest.raises(ValueError, match="identifier cannot contain separator"):
            KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123:456",))

    def test_key_parts_immutable(self) -> None:
        """Test that KeyParts is immutable."""
        parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123",))
        with pytest.raises(AttributeError):
            parts.namespace = "debounce"  # type: ignore


@pytest.mark.unit
class TestKeyBuilder:
    """Test KeyBuilder class."""

    def test_key_builder_creation(self) -> None:
        """Test creating KeyBuilder with valid data."""
        kb = KeyBuilder(app="sentinel")
        assert kb.app == "sentinel"
        assert kb.sep == ":"

    def test_key_builder_custom_separator(self) -> None:
        """Test creating KeyBuilder with custom separator."""
        kb = KeyBuilder(app="sentinel", sep="-")
        assert kb.app == "sentinel"
        assert kb.sep == "-"

    def test_key_builder_empty_app(self) -> None:
        """Test that empty app raises ValueError."""
        with pytest.raises(ValueError, match="app cannot be empty"):
            KeyBuilder(app="")

    def test_key_builder_separator_in_app(self) -> None:
        """Test that separator in app raises ValueError."""
        with pytest.raises(ValueError, match="app cannot contain separator"):
            KeyBuilder(app="sentinel:test")

    @pytest.mark.parametrize(
        "scope,user_id,chat_id,expected_scope",
        [
            (Scope.USER, 123, None, "USER"),
            (Scope.CHAT, None, 456, "CHAT"),
            (Scope.GROUP, 123, 456, "GROUP"),
            (Scope.GLOBAL, None, None, "GLOBAL"),
        ],
    )
    def test_for_update_basic(
        self,
        scope: Scope,
        user_id: int | None,
        chat_id: int | None,
        expected_scope: str,
    ) -> None:
        """Test for_update method with basic parameters."""
        kb = KeyBuilder(app="sentinel")

        identifiers: list[str] = []
        if user_id is not None:
            identifiers.append(str(user_id))
        if chat_id is not None:
            identifiers.append(str(chat_id))
        if scope == Scope.GLOBAL:
            identifiers.append("global")

        parts = KeyParts(
            namespace="throttle", scope=scope, identifiers=tuple(identifiers)
        )

        key = kb.for_update(parts)
        expected = f"sentinel:throttle:{expected_scope}:{':'.join(identifiers)}"
        assert key == expected

    def test_for_update_with_method(self) -> None:
        """Test for_update method with method parameter."""
        kb = KeyBuilder(app="sentinel")
        parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123",))

        key = kb.for_update(parts, method="sendMessage")
        assert key == "sentinel:throttle:USER:123:m=sendMessage"

    def test_for_update_with_bucket(self) -> None:
        """Test for_update method with bucket parameter."""
        kb = KeyBuilder(app="sentinel")
        parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123",))

        key = kb.for_update(parts, bucket="handler_name")
        assert key == "sentinel:throttle:USER:123:b=handler_name"

    def test_for_update_with_both_method_and_bucket(self) -> None:
        """Test for_update method with both method and bucket parameters."""
        kb = KeyBuilder(app="sentinel")
        parts = KeyParts(
            namespace="throttle", scope=Scope.GROUP, identifiers=("123", "456")
        )

        key = kb.for_update(parts, method="sendMessage", bucket="handler_name")
        assert key == "sentinel:throttle:GROUP:123:456:m=sendMessage:b=handler_name"

    def test_for_update_method_with_separator(self) -> None:
        """Test that method with separator raises ValueError."""
        kb = KeyBuilder(app="sentinel")
        parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123",))

        with pytest.raises(ValueError, match="method cannot contain separator"):
            kb.for_update(parts, method="send:Message")

    def test_for_update_bucket_with_separator(self) -> None:
        """Test that bucket with separator raises ValueError."""
        kb = KeyBuilder(app="sentinel")
        parts = KeyParts(namespace="throttle", scope=Scope.USER, identifiers=("123",))

        with pytest.raises(ValueError, match="bucket cannot contain separator"):
            kb.for_update(parts, bucket="handler:name")

    def test_user_method(self) -> None:
        """Test user convenience method."""
        kb = KeyBuilder(app="sentinel")
        key = kb.user("throttle", 123)
        assert key == "sentinel:throttle:USER:123"

    def test_user_method_with_kwargs(self) -> None:
        """Test user method with additional parameters."""
        kb = KeyBuilder(app="sentinel")
        key = kb.user("throttle", 123, method="sendMessage", bucket="handler")
        assert key == "sentinel:throttle:USER:123:m=sendMessage:b=handler"

    def test_chat_method(self) -> None:
        """Test chat convenience method."""
        kb = KeyBuilder(app="sentinel")
        key = kb.chat("throttle", 456)
        assert key == "sentinel:throttle:CHAT:456"

    def test_group_method(self) -> None:
        """Test group convenience method."""
        kb = KeyBuilder(app="sentinel")
        key = kb.group("throttle", 123, 456)
        assert key == "sentinel:throttle:GROUP:123:456"

    def test_global_method(self) -> None:
        """Test global convenience method."""
        kb = KeyBuilder(app="sentinel")
        key = kb.global_("throttle")
        assert key == "sentinel:throttle:GLOBAL:global"

    def test_global_method_with_kwargs(self) -> None:
        """Test global method with additional parameters."""
        kb = KeyBuilder(app="sentinel")
        key = kb.global_("throttle", method="sendMessage", bucket="handler")
        assert key == "sentinel:throttle:GLOBAL:global:m=sendMessage:b=handler"


@pytest.mark.unit
class TestKeyBuilderProperties:
    """Test KeyBuilder properties and invariants."""

    def test_keys_no_whitespace(self) -> None:
        """Test that generated keys never contain whitespace."""
        kb = KeyBuilder(app="sentinel")

        # Test all scopes
        test_cases = [
            kb.user("throttle", 123),
            kb.chat("throttle", 456),
            kb.group("throttle", 123, 456),
            kb.global_("throttle"),
        ]

        for key in test_cases:
            assert " " not in key, f"Key contains whitespace: {key}"
            assert "\t" not in key, f"Key contains tab: {key}"
            assert "\n" not in key, f"Key contains newline: {key}"

    def test_keys_separator_only_as_delimiter(self) -> None:
        """Test that separator appears only as delimiter."""
        kb = KeyBuilder(app="sentinel")

        # Test all scopes
        test_cases = [
            kb.user("throttle", 123),
            kb.chat("throttle", 456),
            kb.group("throttle", 123, 456),
            kb.global_("throttle"),
        ]

        for key in test_cases:
            # Split by separator and check each part
            parts = key.split(":")
            for part in parts:
                # Each part should not contain the separator
                assert ":" not in part, f"Part contains separator: {part}"

    def test_keys_deterministic(self) -> None:
        """Test that same inputs always produce identical keys."""
        kb = KeyBuilder(app="sentinel")

        # Test multiple times with same inputs
        key1 = kb.user("throttle", 123, method="sendMessage", bucket="handler")
        key2 = kb.user("throttle", 123, method="sendMessage", bucket="handler")
        key3 = kb.user("throttle", 123, method="sendMessage", bucket="handler")

        assert key1 == key2 == key3

    def test_keys_collision_resistant(self) -> None:
        """Test that different inputs produce different keys."""
        kb = KeyBuilder(app="sentinel")

        # Different user IDs
        key1 = kb.user("throttle", 123)
        key2 = kb.user("throttle", 456)
        assert key1 != key2

        # Different namespaces
        key3 = kb.user("debounce", 123)
        assert key1 != key3

        # Different scopes
        key4 = kb.chat("throttle", 123)
        assert key1 != key4

        # Different methods
        key5 = kb.user("throttle", 123, method="sendMessage")
        key6 = kb.user("throttle", 123, method="editMessage")
        assert key5 != key6

        # Different buckets
        key7 = kb.user("throttle", 123, bucket="handler1")
        key8 = kb.user("throttle", 123, bucket="handler2")
        assert key7 != key8

    def test_keys_canonical_format(self) -> None:
        """Test that keys follow canonical format."""
        kb = KeyBuilder(app="sentinel")

        # Test canonical format: <app>:<namespace>:<scope>:<id1>[:<id2>]:[m=<method>]:[b=<bucket>]
        key = kb.group("throttle", 123, 456, method="sendMessage", bucket="handler")

        # Should start with app:namespace:scope
        assert key.startswith("sentinel:throttle:GROUP:")

        # Should contain identifiers
        assert "123:456" in key

        # Should contain method
        assert "m=sendMessage" in key

        # Should contain bucket
        assert "b=handler" in key

        # Method should come before bucket
        method_pos = key.find("m=sendMessage")
        bucket_pos = key.find("b=handler")
        assert method_pos < bucket_pos

    @pytest.mark.parametrize(
        "app,namespace,scope,identifiers,method,bucket,expected",
        [
            (
                "sentinel",
                "throttle",
                Scope.USER,
                ("123",),
                None,
                None,
                "sentinel:throttle:USER:123",
            ),
            (
                "sentinel",
                "throttle",
                Scope.CHAT,
                ("456",),
                None,
                None,
                "sentinel:throttle:CHAT:456",
            ),
            (
                "sentinel",
                "throttle",
                Scope.GROUP,
                ("123", "456"),
                None,
                None,
                "sentinel:throttle:GROUP:123:456",
            ),
            (
                "sentinel",
                "throttle",
                Scope.GLOBAL,
                ("global",),
                None,
                None,
                "sentinel:throttle:GLOBAL:global",
            ),
            (
                "sentinel",
                "throttle",
                Scope.USER,
                ("123",),
                "sendMessage",
                None,
                "sentinel:throttle:USER:123:m=sendMessage",
            ),
            (
                "sentinel",
                "throttle",
                Scope.USER,
                ("123",),
                None,
                "handler",
                "sentinel:throttle:USER:123:b=handler",
            ),
            (
                "sentinel",
                "throttle",
                Scope.USER,
                ("123",),
                "sendMessage",
                "handler",
                "sentinel:throttle:USER:123:m=sendMessage:b=handler",
            ),
            (
                "myapp",
                "debounce",
                Scope.GROUP,
                ("789", "012"),
                "editMessage",
                "callback",
                "myapp:debounce:GROUP:789:012:m=editMessage:b=callback",
            ),
        ],
    )
    def test_key_format_examples(
        self,
        app: str,
        namespace: str,
        scope: Scope,
        identifiers: tuple[str, ...],
        method: str | None,
        bucket: str | None,
        expected: str,
    ) -> None:
        """Test specific key format examples."""
        kb = KeyBuilder(app=app)
        parts = KeyParts(namespace=namespace, scope=scope, identifiers=identifiers)
        key = kb.for_update(parts, method=method, bucket=bucket)
        assert key == expected


@pytest.mark.unit
class TestKeyBuilderEdgeCases:
    """Test KeyBuilder edge cases and error conditions."""

    def test_large_user_id(self) -> None:
        """Test with large user ID."""
        kb = KeyBuilder(app="sentinel")
        key = kb.user("throttle", 999999999999)
        assert key == "sentinel:throttle:USER:999999999999"

    def test_negative_user_id(self) -> None:
        """Test with negative user ID."""
        kb = KeyBuilder(app="sentinel")
        key = kb.user("throttle", -123)
        assert key == "sentinel:throttle:USER:-123"

    def test_zero_user_id(self) -> None:
        """Test with zero user ID."""
        kb = KeyBuilder(app="sentinel")
        key = kb.user("throttle", 0)
        assert key == "sentinel:throttle:USER:0"

    def test_long_namespace(self) -> None:
        """Test with long namespace."""
        kb = KeyBuilder(app="sentinel")
        long_namespace = "very_long_namespace_name_for_testing"
        key = kb.user(long_namespace, 123)
        assert key == f"sentinel:{long_namespace}:USER:123"

    def test_long_method(self) -> None:
        """Test with long method name."""
        kb = KeyBuilder(app="sentinel")
        long_method = "very_long_method_name_for_testing_purposes"
        key = kb.user("throttle", 123, method=long_method)
        assert key == f"sentinel:throttle:USER:123:m={long_method}"

    def test_long_bucket(self) -> None:
        """Test with long bucket name."""
        kb = KeyBuilder(app="sentinel")
        long_bucket = "very_long_bucket_name_for_testing_purposes"
        key = kb.user("throttle", 123, bucket=long_bucket)
        assert key == f"sentinel:throttle:USER:123:b={long_bucket}"

    def test_unicode_identifiers(self) -> None:
        """Test with unicode identifiers."""
        kb = KeyBuilder(app="sentinel")
        # This should work as long as no separator characters are used
        unicode_id = "用户123"
        parts = KeyParts(
            namespace="throttle", scope=Scope.USER, identifiers=(unicode_id,)
        )
        key = kb.for_update(parts)
        assert key == f"sentinel:throttle:USER:{unicode_id}"

    def test_unicode_method_bucket(self) -> None:
        """Test with unicode method and bucket names."""
        kb = KeyBuilder(app="sentinel")
        unicode_method = "发送消息"
        unicode_bucket = "处理器"
        key = kb.user("throttle", 123, method=unicode_method, bucket=unicode_bucket)
        assert (
            key == f"sentinel:throttle:USER:123:m={unicode_method}:b={unicode_bucket}"
        )
