"""Unit tests for PolicyRegistry."""

import pytest

from aiogram_sentinel.policy import (
    DebounceCfg,
    Policy,
    PolicyRegistry,
    ThrottleCfg,
)


@pytest.mark.unit
class TestPolicyRegistry:
    """Test PolicyRegistry functionality."""

    def test_register_valid_policy(self) -> None:
        """Test registering a valid policy."""
        registry = PolicyRegistry()

        throttle_cfg = ThrottleCfg(rate=5, per=60)
        policy = Policy("test_throttle", "throttle", throttle_cfg, "Test policy")

        registry.register(policy)

        # Verify policy was registered
        assert registry.get("test_throttle") == policy
        assert len(registry.all()) == 1

    def test_register_duplicate_name_error(self) -> None:
        """Test that registering duplicate policy names raises error."""
        registry = PolicyRegistry()

        throttle_cfg = ThrottleCfg(rate=5, per=60)
        policy1 = Policy("test_policy", "throttle", throttle_cfg)
        policy2 = Policy("test_policy", "debounce", DebounceCfg(window=2))

        registry.register(policy1)

        with pytest.raises(ValueError, match="Policy 'test_policy' already registered"):
            registry.register(policy2)

    def test_get_existing_policy(self) -> None:
        """Test retrieving an existing policy."""
        registry = PolicyRegistry()

        throttle_cfg = ThrottleCfg(rate=10, per=30)
        policy = Policy("user_throttle", "throttle", throttle_cfg)

        registry.register(policy)

        retrieved = registry.get("user_throttle")
        assert retrieved == policy
        assert retrieved.name == "user_throttle"
        assert retrieved.kind == "throttle"

    def test_get_missing_policy_with_suggestions(self) -> None:
        """Test retrieving missing policy with suggestions."""
        registry = PolicyRegistry()

        # Register some policies
        registry.register(
            Policy("user_throttle", "throttle", ThrottleCfg(rate=5, per=60))
        )
        registry.register(Policy("user_debounce", "debounce", DebounceCfg(window=2)))
        registry.register(
            Policy("group_throttle", "throttle", ThrottleCfg(rate=10, per=30))
        )

        # Test with close match
        with pytest.raises(
            ValueError,
            match="Policy 'user_throtle' not found.*Did you mean: user_throttle",
        ):
            registry.get("user_throtle")

        # Test with multiple suggestions
        with pytest.raises(
            ValueError,
            match="Policy 'throttle' not found.*Did you mean: user_throttle, group_throttle",
        ):
            registry.get("throttle")

    def test_get_missing_policy_no_suggestions(self) -> None:
        """Test retrieving missing policy with no suggestions."""
        registry = PolicyRegistry()

        registry.register(
            Policy("user_throttle", "throttle", ThrottleCfg(rate=5, per=60))
        )

        with pytest.raises(ValueError, match="Policy 'completely_different' not found"):
            registry.get("completely_different")

    def test_all_returns_registration_order(self) -> None:
        """Test that all() returns policies in registration order."""
        registry = PolicyRegistry()

        policy1 = Policy("first", "throttle", ThrottleCfg(rate=5, per=60))
        policy2 = Policy("second", "debounce", DebounceCfg(window=2))
        policy3 = Policy("third", "throttle", ThrottleCfg(rate=10, per=30))

        registry.register(policy1)
        registry.register(policy2)
        registry.register(policy3)

        all_policies = registry.all()
        assert len(all_policies) == 3
        assert all_policies[0] == policy1
        assert all_policies[1] == policy2
        assert all_policies[2] == policy3

    def test_clear_removes_all_policies(self) -> None:
        """Test that clear() removes all policies."""
        registry = PolicyRegistry()

        registry.register(Policy("test1", "throttle", ThrottleCfg(rate=5, per=60)))
        registry.register(Policy("test2", "debounce", DebounceCfg(window=2)))

        assert len(registry.all()) == 2

        registry.clear()

        assert len(registry.all()) == 0

        with pytest.raises(ValueError):
            registry.get("test1")


@pytest.mark.unit
class TestThrottleCfg:
    """Test ThrottleCfg validation."""

    def test_valid_throttle_cfg(self) -> None:
        """Test creating valid ThrottleCfg."""
        cfg = ThrottleCfg(rate=5, per=60, method="sendMessage", bucket="test")

        assert cfg.rate == 5
        assert cfg.per == 60
        assert cfg.method == "sendMessage"
        assert cfg.bucket == "test"
        assert cfg.scope is None

    def test_throttle_cfg_negative_rate_error(self) -> None:
        """Test that negative rate raises error."""
        with pytest.raises(ValueError, match="rate must be positive"):
            ThrottleCfg(rate=-1, per=60)

    def test_throttle_cfg_negative_per_error(self) -> None:
        """Test that negative per raises error."""
        with pytest.raises(ValueError, match="per must be positive"):
            ThrottleCfg(rate=5, per=-1)

    def test_throttle_cfg_zero_rate_error(self) -> None:
        """Test that zero rate raises error."""
        with pytest.raises(ValueError, match="rate must be positive"):
            ThrottleCfg(rate=0, per=60)


@pytest.mark.unit
class TestDebounceCfg:
    """Test DebounceCfg validation."""

    def test_valid_debounce_cfg(self) -> None:
        """Test creating valid DebounceCfg."""
        cfg = DebounceCfg(window=2, method="sendMessage", bucket="test")

        assert cfg.window == 2
        assert cfg.method == "sendMessage"
        assert cfg.bucket == "test"
        assert cfg.scope is None

    def test_debounce_cfg_negative_window_error(self) -> None:
        """Test that negative window raises error."""
        with pytest.raises(ValueError, match="window must be positive"):
            DebounceCfg(window=-1)

    def test_debounce_cfg_zero_window_error(self) -> None:
        """Test that zero window raises error."""
        with pytest.raises(ValueError, match="window must be positive"):
            DebounceCfg(window=0)


@pytest.mark.unit
class TestPolicy:
    """Test Policy validation."""

    def test_valid_throttle_policy(self) -> None:
        """Test creating valid throttle policy."""
        cfg = ThrottleCfg(rate=5, per=60)
        policy = Policy("test_throttle", "throttle", cfg, "Test throttle policy")

        assert policy.name == "test_throttle"
        assert policy.kind == "throttle"
        assert policy.cfg == cfg
        assert policy.description == "Test throttle policy"

    def test_valid_debounce_policy(self) -> None:
        """Test creating valid debounce policy."""
        cfg = DebounceCfg(window=2)
        policy = Policy("test_debounce", "debounce", cfg)

        assert policy.name == "test_debounce"
        assert policy.kind == "debounce"
        assert policy.cfg == cfg
        assert policy.description == ""

    def test_empty_name_error(self) -> None:
        """Test that empty name raises error."""
        cfg = ThrottleCfg(rate=5, per=60)

        with pytest.raises(ValueError, match="policy name cannot be empty"):
            Policy("", "throttle", cfg)

    def test_throttle_policy_wrong_cfg_type_error(self) -> None:
        """Test that throttle policy with wrong cfg type raises error."""
        cfg = DebounceCfg(window=2)

        with pytest.raises(ValueError, match="throttle policy must use ThrottleCfg"):
            Policy("test", "throttle", cfg)

    def test_debounce_policy_wrong_cfg_type_error(self) -> None:
        """Test that debounce policy with wrong cfg type raises error."""
        cfg = ThrottleCfg(rate=5, per=60)

        with pytest.raises(ValueError, match="debounce policy must use DebounceCfg"):
            Policy("test", "debounce", cfg)
