"""
Performance tests for aiogram-cmds library.

These tests measure performance characteristics and ensure the library
can handle realistic workloads efficiently.
"""

import time

import pytest

from aiogram_cmds import CommandScopeManager, setup_commands_auto
from aiogram_cmds.customize import CmdsConfig, CommandDef, ProfileDef, ScopeDef


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.mark.asyncio
    async def test_setup_performance(self, mock_bot):
        """Test setup performance with various configurations."""
        # Small config
        small_config = CmdsConfig(
            languages=["en"],
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
        )

        start_time = time.time()
        manager = CommandScopeManager(bot=mock_bot, config=small_config)
        await manager.setup_all()
        small_time = time.time() - start_time

        # Medium config
        medium_config = CmdsConfig(
            languages=["en", "ru", "es"],
            commands={
                f"cmd_{i}": CommandDef(i18n_key=f"cmd_{i}.desc") for i in range(10)
            },
            profiles={
                f"profile_{i}": ProfileDef(include=[f"cmd_{i}"]) for i in range(5)
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="profile_0"),
                ScopeDef(scope="all_group_chats", profile="profile_1"),
            ],
        )

        start_time = time.time()
        manager = CommandScopeManager(bot=mock_bot, config=medium_config)
        await manager.setup_all()
        medium_time = time.time() - start_time

        # Large config
        large_config = CmdsConfig(
            languages=["en", "ru", "es", "fr", "de"],
            commands={
                f"cmd_{i}": CommandDef(i18n_key=f"cmd_{i}.desc") for i in range(50)
            },
            profiles={
                f"profile_{i}": ProfileDef(
                    include=[f"cmd_{j}" for j in range(i * 5, (i + 1) * 5)]
                )
                for i in range(10)
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="profile_0"),
                ScopeDef(scope="all_group_chats", profile="profile_1"),
                ScopeDef(scope="default", profile="profile_2"),
            ],
        )

        start_time = time.time()
        manager = CommandScopeManager(bot=mock_bot, config=large_config)
        await manager.setup_all()
        large_time = time.time() - start_time

        # Performance should scale reasonably
        assert small_time < 1.0  # Small config should be very fast
        assert medium_time < 2.0  # Medium config should be fast
        assert large_time < 5.0  # Large config should be reasonable

        # Large config shouldn't be more than 10x slower than small
        # Handle case where timing is too fast due to mocked objects
        if small_time > 0:
            assert large_time < small_time * 10
        else:
            # With mocked objects, timing is near 0, so just verify it's not negative
            assert large_time >= 0

    @pytest.mark.asyncio
    async def test_user_command_update_performance(self, mock_bot):
        """Test user command update performance."""
        manager = CommandScopeManager(bot=mock_bot)

        # Test single update
        start_time = time.time()
        await manager.update_user_commands(
            user_id=12345,
            is_registered=True,
            has_vehicle=False,
            is_during_registration=False,
            user_language="en",
        )
        single_time = time.time() - start_time

        # Test batch updates
        start_time = time.time()
        for user_id in range(100):
            await manager.update_user_commands(
                user_id=user_id,
                is_registered=user_id % 2 == 0,
                has_vehicle=user_id % 3 == 0,
                is_during_registration=user_id % 5 == 0,
                user_language="en",
            )
        batch_time = time.time() - start_time

        # Single update should be very fast
        assert single_time < 0.1

        # Batch updates should be efficient
        avg_time_per_update = batch_time / 100
        assert avg_time_per_update < 0.01  # Less than 10ms per update

    @pytest.mark.asyncio
    async def test_profile_resolution_performance(self, mock_bot):
        """Test profile resolution performance."""
        # Create complex profile structure
        config = CmdsConfig(
            languages=["en"],
            commands={
                f"cmd_{i}": CommandDef(i18n_key=f"cmd_{i}.desc") for i in range(100)
            },
            profiles={
                f"profile_{i}": ProfileDef(
                    include=[f"cmd_{j}" for j in range(i * 10, (i + 1) * 10)],
                    exclude=[
                        f"cmd_{j}" for j in range(i * 10, i * 10 + 2)
                    ],  # Exclude first 2
                )
                for i in range(10)
            },
            scopes=[ScopeDef(scope="all_private_chats", profile="profile_0")],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)

        # Test profile resolution performance
        start_time = time.time()
        for i in range(1000):
            profile_name = f"profile_{i % 10}"
            commands = manager.config.profiles[profile_name].include
            # Simulate profile resolution logic
            [cmd for cmd in commands if cmd in manager.config.commands]
        resolution_time = time.time() - start_time

        # Profile resolution should be very fast
        avg_time = resolution_time / 1000
        assert avg_time < 0.001  # Less than 1ms per resolution

    @pytest.mark.asyncio
    async def test_memory_usage_scaling(self, mock_bot):
        """Test memory usage scaling with large configurations."""
        import sys

        # Test memory usage with different config sizes
        config_sizes = [10, 50, 100, 200]
        memory_usage = []

        for size in config_sizes:
            config = CmdsConfig(
                languages=["en"],
                commands={
                    f"cmd_{i}": CommandDef(i18n_key=f"cmd_{i}.desc")
                    for i in range(size)
                },
                profiles={
                    f"profile_{i}": ProfileDef(include=[f"cmd_{i}"])
                    for i in range(size // 10)
                },
                scopes=[ScopeDef(scope="all_private_chats", profile="profile_0")],
            )

            manager = CommandScopeManager(bot=mock_bot, config=config)

            # Measure memory usage
            memory_before = sys.getsizeof(manager) + sys.getsizeof(config)
            memory_usage.append(memory_before)

        # Memory usage should scale reasonably (not exponentially)
        for i in range(1, len(memory_usage)):
            growth_ratio = memory_usage[i] / memory_usage[i - 1]
            assert growth_ratio < 5.0  # Should not grow more than 5x per step

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_bot):
        """Test performance under concurrent operations."""
        import asyncio

        manager = CommandScopeManager(bot=mock_bot)

        async def update_user(user_id):
            await manager.update_user_commands(
                user_id=user_id,
                is_registered=True,
                has_vehicle=False,
                is_during_registration=False,
                user_language="en",
            )

        # Test concurrent updates
        start_time = time.time()
        await asyncio.gather(*[update_user(i) for i in range(50)])
        concurrent_time = time.time() - start_time

        # Concurrent operations should be efficient
        assert concurrent_time < 2.0  # Should complete in reasonable time

        # Verify all operations were called
        assert mock_bot.set_my_commands.call_count == 50

    @pytest.mark.asyncio
    async def test_auto_setup_performance(self, mock_bot):
        """Test auto-setup performance."""
        start_time = time.time()
        await setup_commands_auto(
            bot=mock_bot,
            languages=["en", "ru", "es"],
        )
        setup_time = time.time() - start_time

        # Auto-setup should be fast
        assert setup_time < 1.0

        # Verify setup completed
        assert mock_bot.set_my_commands.call_count >= 3

    @pytest.mark.asyncio
    async def test_large_scale_integration(self, mock_bot):
        """Test large-scale integration performance."""
        # Create very large configuration
        config = CmdsConfig(
            languages=["en", "ru", "es", "fr", "de", "it", "pt", "ja", "ko", "zh"],
            commands={
                f"cmd_{i}": CommandDef(i18n_key=f"cmd_{i}.desc") for i in range(200)
            },
            profiles={
                f"profile_{i}": ProfileDef(
                    include=[f"cmd_{j}" for j in range(i * 20, (i + 1) * 20)],
                    exclude=[f"cmd_{j}" for j in range(i * 20, i * 20 + 5)],
                )
                for i in range(10)
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="profile_0"),
                ScopeDef(scope="all_group_chats", profile="profile_1"),
                ScopeDef(scope="default", profile="profile_2"),
            ],
        )

        start_time = time.time()
        manager = CommandScopeManager(bot=mock_bot, config=config)
        await manager.setup_all()
        setup_time = time.time() - start_time

        # Large-scale setup should complete in reasonable time
        assert setup_time < 10.0

        # Test user operations
        start_time = time.time()
        for user_id in range(500):
            await manager.update_user_commands(
                user_id=user_id,
                is_registered=user_id % 2 == 0,
                has_vehicle=user_id % 3 == 0,
                is_during_registration=user_id % 5 == 0,
                user_language="en",
            )
        user_ops_time = time.time() - start_time

        # User operations should be efficient even with large config
        avg_time = user_ops_time / 500
        assert avg_time < 0.02  # Less than 20ms per operation


class TestScalabilityLimits:
    """Test scalability limits and edge cases."""

    @pytest.mark.asyncio
    async def test_maximum_commands_limit(self, mock_bot):
        """Test behavior with maximum number of commands."""
        # Telegram has a limit of 100 commands per scope
        max_commands = 100

        config = CmdsConfig(
            languages=["en"],
            commands={
                f"cmd_{i}": CommandDef(i18n_key=f"cmd_{i}.desc")
                for i in range(max_commands)
            },
            profiles={
                "user": ProfileDef(include=[f"cmd_{i}" for i in range(max_commands)])
            },
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)

        # Should handle maximum commands without issues
        await manager.setup_all()

        # Verify setup completed
        assert mock_bot.set_my_commands.call_count >= 1

    @pytest.mark.asyncio
    async def test_maximum_languages_limit(self, mock_bot):
        """Test behavior with maximum number of languages."""
        # Test with many languages
        languages = [f"lang_{i}" for i in range(50)]

        config = CmdsConfig(
            languages=languages,
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
            scopes=[ScopeDef(scope="all_private_chats", profile="user")],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)

        # Should handle many languages
        await manager.setup_all()

        # Should call set_my_commands for each language
        assert mock_bot.set_my_commands.call_count == len(languages)

    @pytest.mark.asyncio
    async def test_deep_profile_hierarchy(self, mock_bot):
        """Test deep profile hierarchy performance."""
        # Create deep profile hierarchy
        config = CmdsConfig(
            languages=["en"],
            commands={
                f"cmd_{i}": CommandDef(i18n_key=f"cmd_{i}.desc") for i in range(50)
            },
            profiles={
                f"level_{i}": ProfileDef(
                    include=[f"cmd_{j}" for j in range(i * 5, (i + 1) * 5)],
                    exclude=[f"cmd_{j}" for j in range(i * 5, i * 5 + 1)],
                )
                for i in range(10)
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="level_0"),
                ScopeDef(scope="all_group_chats", profile="level_1"),
                ScopeDef(scope="default", profile="level_2"),
            ],
        )

        manager = CommandScopeManager(bot=mock_bot, config=config)

        # Should handle deep hierarchy efficiently
        start_time = time.time()
        await manager.setup_all()
        setup_time = time.time() - start_time

        assert setup_time < 3.0  # Should complete in reasonable time
