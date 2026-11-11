"""
Unit tests for the registry module.
"""

from aiogram_cmds.customize import CmdsConfig, CommandDef, ProfileDef
from aiogram_cmds.registry import CommandRegistry


class TestCommandRegistry:
    """Test CommandRegistry class."""

    def test_registry_initialization(self):
        """Test registry initialization."""
        config = CmdsConfig(
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
        )

        registry = CommandRegistry(config)
        assert registry.cfg == config

    def test_resolve_profile_commands_basic(self):
        """Test basic profile command resolution."""
        config = CmdsConfig(
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "profile": CommandDef(i18n_key="profile.desc"),
            },
            profiles={
                "user": ProfileDef(include=["start", "help"]),
                "admin": ProfileDef(include=["start", "help", "profile"]),
            },
        )

        registry = CommandRegistry(config)

        # Test user profile
        user_commands = registry.resolve_profile_commands("user")
        assert user_commands == ["start", "help"]

        # Test admin profile
        admin_commands = registry.resolve_profile_commands("admin")
        assert admin_commands == ["start", "help", "profile"]

    def test_resolve_profile_commands_with_exclude(self):
        """Test profile command resolution with exclude list."""
        config = CmdsConfig(
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
                "settings": CommandDef(i18n_key="settings.desc"),
            },
            profiles={
                "user": ProfileDef(
                    include=["start", "help", "admin"], exclude=["admin"]
                ),
                "moderator": ProfileDef(
                    include=["start", "help", "admin", "settings"], exclude=["admin"]
                ),
            },
        )

        registry = CommandRegistry(config)

        # Test user profile (admin should be excluded)
        user_commands = registry.resolve_profile_commands("user")
        assert user_commands == ["start", "help"]

        # Test moderator profile (admin should be excluded)
        moderator_commands = registry.resolve_profile_commands("moderator")
        assert moderator_commands == ["start", "help", "settings"]

    def test_resolve_profile_commands_nonexistent_profile(self):
        """Test profile command resolution for nonexistent profile."""
        config = CmdsConfig(
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"user": ProfileDef(include=["start"])},
        )

        registry = CommandRegistry(config)

        # Test nonexistent profile
        commands = registry.resolve_profile_commands("nonexistent")
        assert commands == []

    def test_resolve_profile_commands_missing_commands(self):
        """Test profile command resolution when commands are missing from config."""
        config = CmdsConfig(
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={
                "user": ProfileDef(include=["start", "missing_command"]),
            },
        )

        registry = CommandRegistry(config)

        # Should only return commands that exist in the config
        commands = registry.resolve_profile_commands("user")
        assert commands == ["start"]

    def test_resolve_profile_commands_empty_profile(self):
        """Test profile command resolution for empty profile."""
        config = CmdsConfig(
            commands={"start": CommandDef(i18n_key="start.desc")},
            profiles={"empty": ProfileDef(include=[])},
        )

        registry = CommandRegistry(config)

        commands = registry.resolve_profile_commands("empty")
        assert commands == []

    def test_resolve_profile_commands_profile_with_exclude_only(self):
        """Test profile command resolution with only exclude list."""
        config = CmdsConfig(
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
            },
            profiles={
                "limited": ProfileDef(include=[], exclude=["help"]),
            },
        )

        registry = CommandRegistry(config)

        commands = registry.resolve_profile_commands("limited")
        assert commands == []

    def test_resolve_profile_commands_complex_scenario(self):
        """Test complex profile command resolution scenario."""
        config = CmdsConfig(
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "profile": CommandDef(i18n_key="profile.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
                "settings": CommandDef(i18n_key="settings.desc"),
                "logout": CommandDef(i18n_key="logout.desc"),
            },
            profiles={
                "guest": ProfileDef(include=["start", "help"]),
                "user": ProfileDef(
                    include=["start", "help", "profile", "settings"], exclude=["admin"]
                ),
                "moderator": ProfileDef(
                    include=["start", "help", "profile", "admin"], exclude=["settings"]
                ),
                "admin": ProfileDef(
                    include=["start", "help", "profile", "admin", "settings", "logout"]
                ),
            },
        )

        registry = CommandRegistry(config)

        # Test guest profile
        guest_commands = registry.resolve_profile_commands("guest")
        assert guest_commands == ["start", "help"]

        # Test user profile (admin excluded)
        user_commands = registry.resolve_profile_commands("user")
        assert user_commands == ["start", "help", "profile", "settings"]

        # Test moderator profile (settings excluded)
        moderator_commands = registry.resolve_profile_commands("moderator")
        assert moderator_commands == ["start", "help", "profile", "admin"]

        # Test admin profile (no exclusions)
        admin_commands = registry.resolve_profile_commands("admin")
        assert admin_commands == [
            "start",
            "help",
            "profile",
            "admin",
            "settings",
            "logout",
        ]

    def test_get_command_existing(self):
        """Test getting existing command."""
        config = CmdsConfig(
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
            },
        )

        registry = CommandRegistry(config)

        start_cmd = registry.get_command("start")
        assert start_cmd is not None
        assert start_cmd.i18n_key == "start.desc"

        help_cmd = registry.get_command("help")
        assert help_cmd is not None
        assert help_cmd.i18n_key == "help.desc"

    def test_get_command_nonexistent(self):
        """Test getting nonexistent command."""
        config = CmdsConfig(
            commands={"start": CommandDef(i18n_key="start.desc")},
        )

        registry = CommandRegistry(config)

        cmd = registry.get_command("nonexistent")
        assert cmd is None

    def test_get_command_empty_config(self):
        """Test getting command from empty config."""
        config = CmdsConfig(commands={})

        registry = CommandRegistry(config)

        cmd = registry.get_command("start")
        assert cmd is None

    def test_get_command_with_descriptions(self):
        """Test getting command with inline descriptions."""
        config = CmdsConfig(
            commands={
                "start": CommandDef(
                    i18n_key="start.desc",
                    descriptions={"en": "Start the bot", "ru": "Запустить бота"},
                ),
            },
        )

        registry = CommandRegistry(config)

        start_cmd = registry.get_command("start")
        assert start_cmd is not None
        assert start_cmd.i18n_key == "start.desc"
        assert start_cmd.descriptions["en"] == "Start the bot"
        assert start_cmd.descriptions["ru"] == "Запустить бота"

    def test_registry_with_complex_config(self):
        """Test registry with complex configuration."""
        config = CmdsConfig(
            languages=["en", "ru", "es"],
            fallback_language="en",
            i18n_key_prefix="bot",
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "profile": CommandDef(i18n_key="profile.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
                "settings": CommandDef(i18n_key="settings.desc"),
            },
            profiles={
                "guest": ProfileDef(include=["start", "help"]),
                "user": ProfileDef(include=["start", "help", "profile", "settings"]),
                "admin": ProfileDef(
                    include=["start", "help", "profile", "admin", "settings"]
                ),
            },
            scopes=[],
        )

        registry = CommandRegistry(config)

        # Test all profiles
        guest_commands = registry.resolve_profile_commands("guest")
        assert guest_commands == ["start", "help"]

        user_commands = registry.resolve_profile_commands("user")
        assert user_commands == ["start", "help", "profile", "settings"]

        admin_commands = registry.resolve_profile_commands("admin")
        assert admin_commands == ["start", "help", "profile", "admin", "settings"]

        # Test getting commands
        for cmd_name in ["start", "help", "profile", "admin", "settings"]:
            cmd = registry.get_command(cmd_name)
            assert cmd is not None
            assert cmd.i18n_key == f"{cmd_name}.desc"

    def test_registry_edge_cases(self):
        """Test registry edge cases."""
        config = CmdsConfig(
            commands={
                "cmd1": CommandDef(i18n_key="cmd1.desc"),
                "cmd2": CommandDef(i18n_key="cmd2.desc"),
            },
            profiles={
                "profile1": ProfileDef(include=["cmd1", "cmd2"], exclude=["cmd1"]),
                "profile2": ProfileDef(include=["cmd1"], exclude=["cmd1", "cmd2"]),
                "profile3": ProfileDef(
                    include=["cmd1", "cmd2"], exclude=["cmd1", "cmd2"]
                ),
            },
        )

        registry = CommandRegistry(config)

        # Profile with include and exclude of same command
        commands1 = registry.resolve_profile_commands("profile1")
        assert commands1 == ["cmd2"]  # cmd1 excluded

        # Profile with all commands excluded
        commands2 = registry.resolve_profile_commands("profile2")
        assert commands2 == []  # cmd1 excluded

        # Profile with all commands excluded
        commands3 = registry.resolve_profile_commands("profile3")
        assert commands3 == []  # all commands excluded

    def test_registry_profile_inheritance_simulation(self):
        """Test simulating profile inheritance through include/exclude patterns."""
        config = CmdsConfig(
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
                "profile": CommandDef(i18n_key="profile.desc"),
                "admin": CommandDef(i18n_key="admin.desc"),
            },
            profiles={
                "base": ProfileDef(include=["start", "help"]),
                "user": ProfileDef(include=["start", "help", "profile"]),
                "admin": ProfileDef(include=["start", "help", "profile", "admin"]),
                "limited_admin": ProfileDef(
                    include=["start", "help", "profile", "admin"], exclude=["admin"]
                ),
            },
        )

        registry = CommandRegistry(config)

        # Base profile
        base_commands = registry.resolve_profile_commands("base")
        assert base_commands == ["start", "help"]

        # User profile (extends base)
        user_commands = registry.resolve_profile_commands("user")
        assert user_commands == ["start", "help", "profile"]

        # Admin profile (extends user)
        admin_commands = registry.resolve_profile_commands("admin")
        assert admin_commands == ["start", "help", "profile", "admin"]

        # Limited admin (admin profile but admin command excluded)
        limited_commands = registry.resolve_profile_commands("limited_admin")
        assert limited_commands == ["start", "help", "profile"]
