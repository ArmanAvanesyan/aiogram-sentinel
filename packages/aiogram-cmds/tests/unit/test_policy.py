"""
Unit tests for the policy module.
"""

import pytest

from aiogram_cmds.policy import Flags, default_policy


class TestFlags:
    """Test Flags dataclass."""

    def test_flags_creation(self):
        """Test creating Flags instances."""
        flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=False
        )

        assert flags.is_registered is True
        assert flags.has_vehicle is False
        assert flags.is_during_registration is False

    def test_flags_defaults(self):
        """Test Flags with default values."""
        flags = Flags(is_registered=True, has_vehicle=True)

        assert flags.is_registered is True
        assert flags.has_vehicle is True
        assert flags.is_during_registration is False  # Default value

    def test_flags_immutable(self):
        """Test that Flags is immutable."""
        flags = Flags(is_registered=True, has_vehicle=False)

        # Should not be able to modify fields
        with pytest.raises(AttributeError):
            flags.is_registered = False

    def test_flags_equality(self):
        """Test Flags equality."""
        flags1 = Flags(is_registered=True, has_vehicle=False)
        flags2 = Flags(is_registered=True, has_vehicle=False)
        flags3 = Flags(is_registered=False, has_vehicle=True)

        assert flags1 == flags2
        assert flags1 != flags3

    def test_flags_hash(self):
        """Test Flags hashing."""
        flags1 = Flags(is_registered=True, has_vehicle=False)
        flags2 = Flags(is_registered=True, has_vehicle=False)
        flags3 = Flags(is_registered=False, has_vehicle=True)

        assert hash(flags1) == hash(flags2)
        assert hash(flags1) != hash(flags3)

    def test_flags_repr(self):
        """Test Flags string representation."""
        flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=True
        )
        repr_str = repr(flags)

        assert "Flags" in repr_str
        assert "is_registered=True" in repr_str
        assert "has_vehicle=False" in repr_str
        assert "is_during_registration=True" in repr_str


class TestDefaultPolicy:
    """Test default_policy function."""

    def test_default_policy_guest_user(self):
        """Test default policy for guest user."""
        flags = Flags(is_registered=False, has_vehicle=False)
        commands = default_policy(flags)

        assert isinstance(commands, list)
        assert "start" in commands
        assert "cancel" in commands
        assert "help" not in commands
        assert "profile" not in commands

    def test_default_policy_registered_user(self):
        """Test default policy for registered user."""
        flags = Flags(is_registered=True, has_vehicle=False)
        commands = default_policy(flags)

        assert isinstance(commands, list)
        assert "start" in commands
        assert "help" in commands
        assert "cancel" in commands
        assert "profile" in commands
        assert "settings" in commands

    def test_default_policy_during_registration(self):
        """Test default policy during registration."""
        flags = Flags(
            is_registered=False, has_vehicle=False, is_during_registration=True
        )
        commands = default_policy(flags)

        assert isinstance(commands, list)
        assert "start" in commands
        assert "cancel" in commands
        assert "help" not in commands
        assert "profile" not in commands

    def test_default_policy_registered_during_registration(self):
        """Test default policy for registered user during registration."""
        flags = Flags(
            is_registered=True, has_vehicle=False, is_during_registration=True
        )
        commands = default_policy(flags)

        # Should still be treated as during registration
        assert isinstance(commands, list)
        assert "start" in commands
        assert "cancel" in commands
        assert "help" not in commands
        assert "profile" not in commands

    def test_default_policy_with_vehicle(self):
        """Test default policy for user with vehicle."""
        flags = Flags(is_registered=True, has_vehicle=True)
        commands = default_policy(flags)

        assert isinstance(commands, list)
        assert "start" in commands
        assert "help" in commands
        assert "cancel" in commands
        assert "profile" in commands
        assert "settings" in commands

    def test_default_policy_consistency(self):
        """Test that default policy returns consistent results."""
        flags = Flags(is_registered=True, has_vehicle=False)

        # Call multiple times
        commands1 = default_policy(flags)
        commands2 = default_policy(flags)
        commands3 = default_policy(flags)

        assert commands1 == commands2 == commands3

    def test_default_policy_command_order(self):
        """Test that default policy returns commands in consistent order."""
        flags = Flags(is_registered=True, has_vehicle=False)
        commands = default_policy(flags)

        # Should be in a consistent order
        expected_order = ["start", "help", "cancel", "profile", "settings"]
        assert commands == expected_order

    def test_default_policy_all_flag_combinations(self):
        """Test default policy with all possible flag combinations."""
        flag_combinations = [
            (False, False, False),  # Guest
            (False, False, True),  # During registration
            (True, False, False),  # Registered user
            (True, False, True),  # Registered during registration
            (True, True, False),  # Registered with vehicle
            (True, True, True),  # Registered with vehicle during registration
        ]

        for is_registered, has_vehicle, is_during_registration in flag_combinations:
            flags = Flags(
                is_registered=is_registered,
                has_vehicle=has_vehicle,
                is_during_registration=is_during_registration,
            )

            commands = default_policy(flags)

            assert isinstance(commands, list)
            assert len(commands) > 0
            assert "start" in commands  # Always present

            # During registration should only have start and cancel
            if is_during_registration or not is_registered:
                assert commands == ["start", "cancel"]
            else:
                assert len(commands) > 2
                assert "help" in commands
                assert "profile" in commands


class TestCommandPolicyProtocol:
    """Test CommandPolicy protocol."""

    def test_command_policy_protocol(self):
        """Test that functions can be used as CommandPolicy."""

        def custom_policy(flags: Flags) -> list[str]:
            if flags.is_registered:
                return ["start", "help", "profile"]
            return ["start", "help"]

        # Should work without errors
        flags = Flags(is_registered=True, has_vehicle=False)
        commands = custom_policy(flags)

        assert isinstance(commands, list)
        assert "start" in commands
        assert "help" in commands
        assert "profile" in commands

    def test_command_policy_with_different_flags(self):
        """Test CommandPolicy with different flag combinations."""

        def custom_policy(flags: Flags) -> list[str]:
            if flags.is_during_registration:
                return ["start", "cancel"]
            elif flags.is_registered:
                return ["start", "help", "profile", "settings"]
            else:
                return ["start", "help"]

        # Test different flag combinations
        test_cases = [
            (Flags(is_registered=False, has_vehicle=False), ["start", "help"]),
            (
                Flags(is_registered=True, has_vehicle=False),
                ["start", "help", "profile", "settings"],
            ),
            (
                Flags(
                    is_registered=False, has_vehicle=False, is_during_registration=True
                ),
                ["start", "cancel"],
            ),
        ]

        for flags, expected in test_cases:
            result = custom_policy(flags)
            assert result == expected

    def test_command_policy_error_handling(self):
        """Test CommandPolicy error handling."""

        def failing_policy(flags: Flags) -> list[str]:
            if flags.is_registered:
                raise Exception("Policy error")
            return ["start", "help"]

        # Should handle errors gracefully
        flags = Flags(is_registered=False, has_vehicle=False)
        commands = failing_policy(flags)
        assert commands == ["start", "help"]

        # Should raise exception for registered user
        flags = Flags(is_registered=True, has_vehicle=False)
        with pytest.raises(Exception, match="Policy error"):
            failing_policy(flags)


class TestProfileResolverProtocol:
    """Test ProfileResolver protocol."""

    def test_profile_resolver_protocol(self):
        """Test that functions can be used as ProfileResolver."""

        def custom_resolver(flags: Flags) -> str:
            if flags.is_registered:
                return "user"
            return "guest"

        # Should work without errors
        flags = Flags(is_registered=True, has_vehicle=False)
        profile = custom_resolver(flags)

        assert isinstance(profile, str)
        assert profile == "user"

    def test_profile_resolver_with_different_flags(self):
        """Test ProfileResolver with different flag combinations."""

        def custom_resolver(flags: Flags) -> str:
            if flags.is_during_registration:
                return "registering"
            elif flags.is_registered and flags.has_vehicle:
                return "premium"
            elif flags.is_registered:
                return "user"
            else:
                return "guest"

        # Test different flag combinations
        test_cases = [
            (Flags(is_registered=False, has_vehicle=False), "guest"),
            (Flags(is_registered=True, has_vehicle=False), "user"),
            (Flags(is_registered=True, has_vehicle=True), "premium"),
            (
                Flags(
                    is_registered=False, has_vehicle=False, is_during_registration=True
                ),
                "registering",
            ),
        ]

        for flags, expected in test_cases:
            result = custom_resolver(flags)
            assert result == expected

    def test_profile_resolver_error_handling(self):
        """Test ProfileResolver error handling."""

        def failing_resolver(flags: Flags) -> str:
            if flags.is_registered:
                raise Exception("Resolver error")
            return "guest"

        # Should handle errors gracefully
        flags = Flags(is_registered=False, has_vehicle=False)
        profile = failing_resolver(flags)
        assert profile == "guest"

        # Should raise exception for registered user
        flags = Flags(is_registered=True, has_vehicle=False)
        with pytest.raises(Exception, match="Resolver error"):
            failing_resolver(flags)


class TestPolicyIntegration:
    """Test policy integration with other components."""

    def test_policy_with_manager(self, mock_bot, basic_config):
        """Test policy integration with CommandScopeManager."""

        def custom_policy(flags: Flags) -> list[str]:
            if flags.is_registered:
                return ["start", "help", "profile"]
            return ["start", "help"]

        from aiogram_cmds import CommandScopeManager

        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, policy=custom_policy
        )

        assert manager.policy == custom_policy

        # Test policy with different flags
        guest_flags = Flags(is_registered=False, has_vehicle=False)
        user_flags = Flags(is_registered=True, has_vehicle=False)

        assert custom_policy(guest_flags) == ["start", "help"]
        assert custom_policy(user_flags) == ["start", "help", "profile"]

    def test_profile_resolver_with_manager(self, mock_bot, basic_config):
        """Test profile resolver integration with CommandScopeManager."""

        def custom_resolver(flags: Flags) -> str:
            if flags.is_registered:
                return "user"
            return "guest"

        from aiogram_cmds import CommandScopeManager

        manager = CommandScopeManager(
            bot=mock_bot, config=basic_config, profile_resolver=custom_resolver
        )

        assert manager.profile_resolver == custom_resolver

        # Test resolver with different flags
        guest_flags = Flags(is_registered=False, has_vehicle=False)
        user_flags = Flags(is_registered=True, has_vehicle=False)

        assert custom_resolver(guest_flags) == "guest"
        assert custom_resolver(user_flags) == "user"

    def test_policy_and_resolver_consistency(self):
        """Test consistency between policy and resolver."""

        def policy(flags: Flags) -> list[str]:
            if flags.is_registered:
                return ["start", "help", "profile"]
            return ["start", "help"]

        def resolver(flags: Flags) -> str:
            if flags.is_registered:
                return "user"
            return "guest"

        # Test with same flags
        flags = Flags(is_registered=True, has_vehicle=False)

        commands = policy(flags)
        profile = resolver(flags)

        assert isinstance(commands, list)
        assert isinstance(profile, str)
        assert len(commands) > 0
        assert len(profile) > 0

    def test_policy_performance(self):
        """Test policy performance."""
        import time

        flags = Flags(is_registered=True, has_vehicle=False)

        # Warm up
        for _ in range(10):
            default_policy(flags)

        # Benchmark
        start_time = time.time()
        iterations = 10000

        for _ in range(iterations):
            default_policy(flags)

        end_time = time.time()
        duration = end_time - start_time

        # Should be very fast
        assert duration < 0.1  # Less than 100ms for 10k iterations

        # Average time per call should be reasonable
        avg_time = duration / iterations
        assert avg_time < 0.00001  # Less than 10μs per call
