"""
aiogram_cmds - Command builder & scope manager for aiogram bots.

This package provides both simple and full customizable modes for managing
Telegram bot commands with i18n support, profiles, and multiple scope types.

Simple Mode:
    from aiogram_cmds import CommandScopeManager, load_settings, build_translator_from_i18n

    settings = load_settings()
    translator = build_translator_from_i18n(i18n)
    manager = CommandScopeManager(bot, settings=settings, translator=translator)
    await manager.setup_all()

Full Customizable Mode:
    from aiogram_cmds import CmdsConfig, CommandDef, ProfileDef, ScopeDef, MenuButtonDef

    config = CmdsConfig(
        commands={"start": CommandDef(i18n_key="start.desc")},
        profiles={"guest": ProfileDef(include=["start"])},
        scopes=[ScopeDef(scope="all_private_chats", profile="guest")],
    )
    manager = CommandScopeManager(bot, config=config, profile_resolver=my_resolver)

Auto-Setup (Recommended):
    from aiogram_cmds.auto_setup import setup_commands_auto

    async def on_startup():
        command_manager = await setup_commands_auto(bot)
"""

from .apply import apply_config
from .auto_setup import setup_commands_auto
from .builder import build_bot_commands
from .customize import CmdsConfig, CommandDef, MenuButtonDef, ProfileDef, ScopeDef
from .dynamic import set_user_profile
from .manager import CommandScopeManager
from .policy import CommandPolicy, Flags, ProfileResolver, default_policy
from .settings import CmdsSettings, load_settings
from .translator import Translator, build_translator_from_i18n, noop_translator
from .version import __version__ as __version__

__author__ = "aiogram_cmds contributors"
__description__ = "Command builder & scope manager for aiogram bots"

__all__ = [
    # Simple / classic
    "build_bot_commands",
    "CommandScopeManager",
    "Flags",
    "CommandPolicy",
    "default_policy",
    "Translator",
    "build_translator_from_i18n",
    "noop_translator",
    "CmdsSettings",
    "load_settings",
    # Full customizable
    "CmdsConfig",
    "CommandDef",
    "ProfileDef",
    "ScopeDef",
    "MenuButtonDef",
    "apply_config",
    "set_user_profile",
    "ProfileResolver",
    # Auto-setup (convenience)
    "setup_commands_auto",
]
