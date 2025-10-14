"""Integration tests for policy registry workflow."""

import pytest

from aiogram_sentinel import (
    DebounceCfg,
    Policy,
    Scope,
    SentinelConfig,
    ThrottleCfg,
    policy,
    registry,
)
from aiogram_sentinel.middlewares.policy_resolver import PolicyResolverMiddleware


@pytest.mark.integration
class TestPolicyIntegration:
    """Test end-to-end policy workflow."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Clear registry for each test
        registry.clear()

    def test_register_and_attach_single_policy(self) -> None:
        """Test registering and attaching single policy."""
        # Register policy
        throttle_cfg = ThrottleCfg(rate=5, per=60, scope=Scope.USER)
        user_throttle = Policy("user_throttle", "throttle", throttle_cfg)
        registry.register(user_throttle)

        # Attach to handler
        @policy("user_throttle")
        async def handler():
            return "test"

        # Verify policy attachment
        assert hasattr(handler, "__sentinel_policies__")  # type: ignore[attr-defined]
        assert handler.__sentinel_policies__ == ("user_throttle",)  # type: ignore[attr-defined]

        # Test policy resolution
        cfg = SentinelConfig()
        resolver = PolicyResolverMiddleware(registry, cfg)
        throttle_cfg_result, debounce_cfg_result = (
            resolver.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result == throttle_cfg
        assert debounce_cfg_result is None

    def test_compose_throttle_and_debounce_policies(self) -> None:
        """Test composing throttle and debounce policies."""
        # Register policies
        throttle_cfg = ThrottleCfg(rate=5, per=60, scope=Scope.USER)
        debounce_cfg = DebounceCfg(window=2, scope=Scope.USER)

        user_throttle = Policy("user_throttle", "throttle", throttle_cfg)
        user_debounce = Policy("user_debounce", "debounce", debounce_cfg)

        registry.register(user_throttle)
        registry.register(user_debounce)

        # Attach both policies to handler
        @policy("user_throttle", "user_debounce")
        async def handler():
            return "test"

        # Test policy resolution
        cfg = SentinelConfig()
        resolver = PolicyResolverMiddleware(registry, cfg)
        throttle_cfg_result, debounce_cfg_result = (
            resolver.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result == throttle_cfg
        assert debounce_cfg_result == debounce_cfg

    def test_policy_override_multiple_same_kind(self) -> None:
        """Test policy override with multiple same-kind policies."""
        # Register policies
        throttle_cfg1 = ThrottleCfg(rate=5, per=60)
        throttle_cfg2 = ThrottleCfg(rate=10, per=30)

        throttle1 = Policy("throttle1", "throttle", throttle_cfg1)
        throttle2 = Policy("throttle2", "throttle", throttle_cfg2)

        registry.register(throttle1)
        registry.register(throttle2)

        # Attach both policies (last should win)
        @policy("throttle1", "throttle2")
        async def handler():
            return "test"

        # Test policy resolution
        cfg = SentinelConfig()
        resolver = PolicyResolverMiddleware(registry, cfg)
        throttle_cfg_result, debounce_cfg_result = (
            resolver.resolve_configurations_for_testing(handler)
        )

        assert throttle_cfg_result == throttle_cfg2  # Last wins
        assert debounce_cfg_result is None

    def test_scope_cap_enforcement(self) -> None:
        """Test scope cap enforcement in policy resolution."""
        # Register policy with USER scope cap
        throttle_cfg = ThrottleCfg(rate=5, per=60, scope=Scope.USER)
        user_throttle = Policy("user_throttle", "throttle", throttle_cfg)
        registry.register(user_throttle)

        @policy("user_throttle")
        async def handler():  # type: ignore[unused-function]
            return "test"

        # Test with user and chat available - should resolve to USER
        from aiogram_sentinel.policy import resolve_scope

        result = resolve_scope(user_id=123, chat_id=456, cap=Scope.USER)
        assert result == Scope.USER

        # Test with no user available - should return None
        result = resolve_scope(user_id=None, chat_id=456, cap=Scope.USER)
        assert result is None

    def test_legacy_decorator_still_works_with_deprecation(self) -> None:
        """Test that legacy decorators still work with deprecation warning."""
        import warnings

        from aiogram_sentinel import debounce, rate_limit

        # Create handler with legacy decorators
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @rate_limit(5, 60, scope="user")
            @debounce(2, scope="chat")
            async def legacy_handler():
                return "test"

            # Check deprecation warnings were emitted
            assert len(w) == 2
            assert all(
                issubclass(warning.category, DeprecationWarning) for warning in w
            )
            assert any(
                "@rate_limit is deprecated" in str(warning.message) for warning in w
            )
            assert any(
                "@debounce is deprecated" in str(warning.message) for warning in w
            )

        # Test legacy resolution still works
        cfg = SentinelConfig()
        resolver = PolicyResolverMiddleware(registry, cfg)
        throttle_cfg_result, debounce_cfg_result = (
            resolver.resolve_configurations_for_testing(legacy_handler)
        )

        assert throttle_cfg_result is not None
        assert throttle_cfg_result.rate == 5
        assert throttle_cfg_result.per == 60
        assert throttle_cfg_result.scope == Scope.USER

        assert debounce_cfg_result is not None
        assert debounce_cfg_result.window == 2
        assert debounce_cfg_result.scope == Scope.CHAT

    def test_mixed_legacy_and_policy_shows_warning(self) -> None:
        """Test mixed legacy and policy shows warning but policy wins."""
        import warnings

        from aiogram_sentinel import rate_limit

        # Register policy
        throttle_cfg = ThrottleCfg(rate=10, per=30)
        user_throttle = Policy("user_throttle", "throttle", throttle_cfg)
        registry.register(user_throttle)

        # Create handler with both policy and legacy decorator
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @policy("user_throttle")
            @rate_limit(5, 60)  # This should be ignored
            async def mixed_handler():
                return "test"

        # Test resolution
        cfg = SentinelConfig()
        resolver = PolicyResolverMiddleware(registry, cfg)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            throttle_cfg_result, debounce_cfg_result = (
                resolver.resolve_configurations_for_testing(mixed_handler)
            )

            # Policy should win
            assert throttle_cfg_result == throttle_cfg
            assert debounce_cfg_result is None

            # Warning should be emitted about conflict
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "@rate_limit is deprecated" in str(w[0].message)

    def test_policy_with_method_and_bucket(self) -> None:
        """Test policy with method and bucket parameters."""
        # Register policy with method and bucket
        throttle_cfg = ThrottleCfg(
            rate=5, per=60, scope=Scope.USER, method="sendMessage", bucket="test_bucket"
        )
        user_throttle = Policy("user_throttle", "throttle", throttle_cfg)
        registry.register(user_throttle)

        @policy("user_throttle")
        async def handler():
            return "test"

        # Test policy resolution
        cfg = SentinelConfig()
        resolver = PolicyResolverMiddleware(registry, cfg)
        throttle_cfg_result, debounce_cfg_result = (
            resolver.resolve_configurations_for_testing(  # type: ignore[unused-variable]
                handler
            )
        )

        assert throttle_cfg_result == throttle_cfg
        assert throttle_cfg_result is not None
        assert throttle_cfg_result.method == "sendMessage"
        assert throttle_cfg_result.bucket == "test_bucket"
        # debounce_cfg_result is None for throttle-only policy

    def test_error_handling_missing_policy(self) -> None:
        """Test error handling for missing policy."""
        # Don't register any policies

        @policy("missing_policy")
        async def handler():
            return "test"

        # Test policy resolution should raise error
        cfg = SentinelConfig()
        resolver = PolicyResolverMiddleware(registry, cfg)

        with pytest.raises(
            ValueError, match="Failed to resolve policy 'missing_policy'"
        ):
            resolver.resolve_configurations_for_testing(handler)

    def test_error_handling_invalid_policy_name(self) -> None:
        """Test error handling for invalid policy name."""
        # Register some policies for suggestions
        registry.register(
            Policy("user_throttle", "throttle", ThrottleCfg(rate=5, per=60))
        )
        registry.register(Policy("user_debounce", "debounce", DebounceCfg(window=2)))

        @policy("user_throtle")  # Typo
        async def handler():
            return "test"

        # Test policy resolution should raise error with suggestions
        cfg = SentinelConfig()
        resolver = PolicyResolverMiddleware(registry, cfg)

        with pytest.raises(ValueError, match="Did you mean: user_throttle"):
            resolver.resolve_configurations_for_testing(handler)
