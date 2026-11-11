"""Unit tests for PolicyResolverMiddleware."""

import warnings
from unittest.mock import Mock

import pytest

from aiogram_sentinel.config import SentinelConfig
from aiogram_sentinel.middlewares.policy_resolver import PolicyResolverMiddleware
from aiogram_sentinel.policy import (
    DebounceCfg,
    Policy,
    PolicyRegistry,
    ThrottleCfg,
)
from aiogram_sentinel.scopes import Scope


@pytest.mark.unit
class TestPolicyResolverMiddleware:
    """Test PolicyResolverMiddleware functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.registry = PolicyRegistry()
        self.cfg = SentinelConfig()
        self.middleware = PolicyResolverMiddleware(self.registry, self.cfg)

    def test_resolves_single_throttle_policy(self) -> None:
        """Test resolving single throttle policy."""
        # Register policy
        throttle_cfg = ThrottleCfg(rate=5, per=60, scope=Scope.USER)
        policy = Policy("user_throttle", "throttle", throttle_cfg)
        self.registry.register(policy)

        # Create handler with policy
        handler = Mock()
        handler.__sentinel_policies__ = ("user_throttle",)

        # Resolve configurations
        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result == throttle_cfg
        assert debounce_cfg_result is None

    def test_resolves_single_debounce_policy(self) -> None:
        """Test resolving single debounce policy."""
        # Register policy
        debounce_cfg = DebounceCfg(window=2, scope=Scope.CHAT)
        policy = Policy("chat_debounce", "debounce", debounce_cfg)
        self.registry.register(policy)

        # Create handler with policy
        handler = Mock()
        handler.__sentinel_policies__ = ("chat_debounce",)

        # Resolve configurations
        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result is None
        assert debounce_cfg_result == debounce_cfg

    def test_resolves_multiple_policies_same_kind_last_wins(self) -> None:
        """Test resolving multiple policies of same kind - last wins."""
        # Register policies
        throttle_cfg1 = ThrottleCfg(rate=5, per=60)
        throttle_cfg2 = ThrottleCfg(rate=10, per=30)

        policy1 = Policy("throttle1", "throttle", throttle_cfg1)
        policy2 = Policy("throttle2", "throttle", throttle_cfg2)

        self.registry.register(policy1)
        self.registry.register(policy2)

        # Create handler with both policies
        handler = Mock()
        handler.__sentinel_policies__ = ("throttle1", "throttle2")

        # Resolve configurations
        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result == throttle_cfg2  # Last wins
        assert debounce_cfg_result is None

    def test_resolves_multiple_policies_different_kinds_all_applied(self) -> None:
        """Test resolving multiple policies of different kinds - all applied."""
        # Register policies
        throttle_cfg = ThrottleCfg(rate=5, per=60)
        debounce_cfg = DebounceCfg(window=2)

        throttle_policy = Policy("user_throttle", "throttle", throttle_cfg)
        debounce_policy = Policy("user_debounce", "debounce", debounce_cfg)

        self.registry.register(throttle_policy)
        self.registry.register(debounce_policy)

        # Create handler with both policies
        handler = Mock()
        handler.__sentinel_policies__ = ("user_throttle", "user_debounce")

        # Resolve configurations
        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result == throttle_cfg
        assert debounce_cfg_result == debounce_cfg

    def test_legacy_throttle_decorator_compatibility(self) -> None:
        """Test compatibility with legacy throttle decorator."""
        # Create handler with legacy decorator
        handler = Mock()
        handler.sentinel_rate_limit = (5, 60, "user")

        # Resolve configurations
        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result is not None
        assert throttle_cfg_result.rate == 5
        assert throttle_cfg_result.per == 60
        assert throttle_cfg_result.scope == Scope.USER
        assert debounce_cfg_result is None

    def test_legacy_debounce_decorator_compatibility(self) -> None:
        """Test compatibility with legacy debounce decorator."""
        # Create handler with legacy decorator
        handler = Mock()
        handler.sentinel_debounce = (2, "chat")

        # Resolve configurations
        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result is None
        assert debounce_cfg_result is not None
        assert debounce_cfg_result.window == 2
        assert debounce_cfg_result.scope == Scope.CHAT

    def test_legacy_dict_config_compatibility(self) -> None:
        """Test compatibility with legacy dict config."""
        # Create handler with legacy dict config
        handler = Mock()
        handler.sentinel_rate_limit = {
            "limit": 10,
            "window": 30,
            "scope": "group",
            "method": "sendMessage",
            "bucket": "test",
        }

        # Resolve configurations
        throttle_cfg_result, debounce_cfg_result = (  # type: ignore[unused-variable]
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result is not None
        assert throttle_cfg_result.rate == 10
        assert throttle_cfg_result.per == 30
        assert throttle_cfg_result.scope == Scope.GROUP
        assert throttle_cfg_result.method == "sendMessage"
        assert throttle_cfg_result.bucket == "test"
        # debounce_cfg_result is None for throttle-only policy

    def test_policy_wins_over_legacy_decorator(self) -> None:
        """Test that policy wins over legacy decorator with warning."""
        # Register policy
        throttle_cfg = ThrottleCfg(rate=5, per=60)
        policy = Policy("user_throttle", "throttle", throttle_cfg)
        self.registry.register(policy)

        # Create handler with both policy and legacy decorator
        handler = Mock()
        handler.__sentinel_policies__ = ("user_throttle",)
        handler.sentinel_rate_limit = (10, 30)

        # Resolve configurations with warning capture
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            throttle_cfg_result, debounce_cfg_result = (
                self.middleware.resolve_configurations_for_testing(handler)
            )

            # Policy should win
            assert throttle_cfg_result == throttle_cfg
            assert debounce_cfg_result is None

            # Warning should be emitted
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "@rate_limit is deprecated" in str(w[0].message)

    def test_missing_policy_raises_error_with_suggestions(self) -> None:
        """Test that missing policy raises error with suggestions."""
        # Register some policies for suggestions
        self.registry.register(
            Policy("user_throttle", "throttle", ThrottleCfg(rate=5, per=60))
        )
        self.registry.register(
            Policy("user_debounce", "debounce", DebounceCfg(window=2))
        )

        # Create handler with missing policy
        handler = Mock()
        handler.__sentinel_policies__ = ("user_throtle",)  # Typo
        handler.__name__ = "test_handler"

        # Should raise error with suggestions
        with pytest.raises(
            ValueError,
            match="Failed to resolve policy 'user_throtle' for handler 'test_handler'.*Did you mean: user_throttle",
        ):
            self.middleware.resolve_configurations_for_testing(handler)

    def test_invalid_legacy_config_logs_warning(self) -> None:
        """Test that invalid legacy config logs warning."""
        # Create handler with invalid legacy config
        handler = Mock()
        handler.sentinel_rate_limit = "invalid_config"

        # Should not raise error, but log warning
        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result is None
        assert debounce_cfg_result is None

    def test_no_policies_or_legacy_returns_none(self) -> None:
        """Test that handler with no policies or legacy decorators returns None."""
        handler = Mock()

        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result is None
        assert debounce_cfg_result is None

    def test_handler_without_sentinel_policies_attribute(self) -> None:
        """Test handler without __sentinel_policies__ attribute."""
        handler = Mock()
        # Don't set __sentinel_policies__ attribute

        throttle_cfg_result, debounce_cfg_result = (
            self.middleware.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result is None
        assert debounce_cfg_result is None
