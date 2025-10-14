"""Unit tests for scope resolution and coercion."""

import warnings

import pytest

from aiogram_sentinel.policy import coerce_scope, resolve_scope
from aiogram_sentinel.scopes import Scope


@pytest.mark.unit
class TestScopeCoercion:
    """Test scope coercion functionality."""

    def test_coerce_scope_enum(self) -> None:
        """Test coercing Scope enum returns as-is."""
        assert coerce_scope(Scope.USER) == Scope.USER
        assert coerce_scope(Scope.CHAT) == Scope.CHAT
        assert coerce_scope(Scope.GROUP) == Scope.GROUP
        assert coerce_scope(Scope.GLOBAL) == Scope.GLOBAL

    def test_coerce_scope_none(self) -> None:
        """Test coercing None returns None."""
        assert coerce_scope(None) is None

    def test_coerce_scope_string_valid(self) -> None:
        """Test coercing valid string scopes."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            assert coerce_scope("user") == Scope.USER
            assert coerce_scope("chat") == Scope.CHAT
            assert coerce_scope("group") == Scope.GROUP
            assert coerce_scope("global") == Scope.GLOBAL

            # Check deprecation warning was emitted
            assert len(w) == 4
            assert all(
                issubclass(warning.category, DeprecationWarning) for warning in w
            )
            assert all(
                "String scope is deprecated" in str(warning.message) for warning in w
            )

    def test_coerce_scope_string_case_insensitive(self) -> None:
        """Test that string coercion is case insensitive."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            assert coerce_scope("USER") == Scope.USER
            assert coerce_scope("Chat") == Scope.CHAT
            assert coerce_scope("GROUP") == Scope.GROUP
            assert coerce_scope("Global") == Scope.GLOBAL

    def test_coerce_scope_string_invalid(self) -> None:
        """Test that invalid string scope raises error."""
        with pytest.raises(ValueError, match="Invalid scope: invalid"):
            coerce_scope("invalid")


@pytest.mark.unit
class TestScopeResolution:
    """Test scope resolution with cap logic."""

    def test_resolve_scope_no_cap_user_chat_available(self) -> None:
        """Test resolving scope with no cap, user and chat available."""
        # Should pick USER (most specific)
        result = resolve_scope(user_id=123, chat_id=456, cap=None)
        assert result == Scope.USER

    def test_resolve_scope_no_cap_user_only(self) -> None:
        """Test resolving scope with no cap, user only."""
        result = resolve_scope(user_id=123, chat_id=None, cap=None)
        assert result == Scope.USER

    def test_resolve_scope_no_cap_chat_only(self) -> None:
        """Test resolving scope with no cap, chat only."""
        result = resolve_scope(user_id=None, chat_id=456, cap=None)
        assert result == Scope.CHAT

    def test_resolve_scope_no_cap_neither_available(self) -> None:
        """Test resolving scope with no cap, neither available."""
        result = resolve_scope(user_id=None, chat_id=None, cap=None)
        assert result == Scope.GLOBAL

    def test_resolve_scope_cap_user_with_user_chat(self) -> None:
        """Test resolving scope with USER cap, user and chat available."""
        # Should pick USER (most specific within cap)
        result = resolve_scope(user_id=123, chat_id=456, cap=Scope.USER)
        assert result == Scope.USER

    def test_resolve_scope_cap_user_user_only(self) -> None:
        """Test resolving scope with USER cap, user only."""
        result = resolve_scope(user_id=123, chat_id=None, cap=Scope.USER)
        assert result == Scope.USER

    def test_resolve_scope_cap_user_no_user(self) -> None:
        """Test resolving scope with USER cap, no user available."""
        result = resolve_scope(user_id=None, chat_id=456, cap=Scope.USER)
        assert result is None

    def test_resolve_scope_cap_chat_with_user_chat(self) -> None:
        """Test resolving scope with CHAT cap, user and chat available."""
        # Should pick USER (more specific than CHAT)
        result = resolve_scope(user_id=123, chat_id=456, cap=Scope.CHAT)
        assert result == Scope.USER

    def test_resolve_scope_cap_chat_chat_only(self) -> None:
        """Test resolving scope with CHAT cap, chat only."""
        result = resolve_scope(user_id=None, chat_id=456, cap=Scope.CHAT)
        assert result == Scope.CHAT

    def test_resolve_scope_cap_chat_no_chat(self) -> None:
        """Test resolving scope with CHAT cap, no chat available."""
        result = resolve_scope(user_id=123, chat_id=None, cap=Scope.CHAT)
        assert result == Scope.USER

    def test_resolve_scope_cap_group_with_user_chat(self) -> None:
        """Test resolving scope with GROUP cap, user and chat available."""
        # Should pick USER (most specific within GROUP cap)
        result = resolve_scope(user_id=123, chat_id=456, cap=Scope.GROUP)
        assert result == Scope.USER

    def test_resolve_scope_cap_group_user_only(self) -> None:
        """Test resolving scope with GROUP cap, user only."""
        result = resolve_scope(user_id=123, chat_id=None, cap=Scope.GROUP)
        assert result == Scope.USER

    def test_resolve_scope_cap_group_chat_only(self) -> None:
        """Test resolving scope with GROUP cap, chat only."""
        result = resolve_scope(user_id=None, chat_id=456, cap=Scope.GROUP)
        assert result == Scope.CHAT

    def test_resolve_scope_cap_group_neither(self) -> None:
        """Test resolving scope with GROUP cap, neither available."""
        result = resolve_scope(user_id=None, chat_id=None, cap=Scope.GROUP)
        assert result is None

    def test_resolve_scope_cap_global_always_works(self) -> None:
        """Test resolving scope with GLOBAL cap always works."""
        # With user and chat
        result = resolve_scope(user_id=123, chat_id=456, cap=Scope.GLOBAL)
        assert result == Scope.USER

        # With user only
        result = resolve_scope(user_id=123, chat_id=None, cap=Scope.GLOBAL)
        assert result == Scope.USER

        # With chat only
        result = resolve_scope(user_id=None, chat_id=456, cap=Scope.GLOBAL)
        assert result == Scope.CHAT

        # With neither
        result = resolve_scope(user_id=None, chat_id=None, cap=Scope.GLOBAL)
        assert result == Scope.GLOBAL

    def test_resolve_scope_specificity_order(self) -> None:
        """Test that specificity order is USER > CHAT > GROUP > GLOBAL."""
        # All available - should pick USER
        result = resolve_scope(user_id=123, chat_id=456, cap=None)
        assert result == Scope.USER

        # No user - should pick CHAT
        result = resolve_scope(user_id=None, chat_id=456, cap=None)
        assert result == Scope.CHAT

        # No user or chat - should pick GLOBAL
        result = resolve_scope(user_id=None, chat_id=None, cap=None)
        assert result == Scope.GLOBAL
