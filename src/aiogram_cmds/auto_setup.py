"""
Auto-setup utilities for aiogram_cmds.

This module provides convenient functions to automatically set up command management
with minimal configuration, making it easy to integrate into __main__.py.
"""

import logging
from typing import cast

from aiogram import Bot

from .customize import CmdsConfig, CommandDef, MenuButtonDef, ProfileDef, ScopeDef
from .manager import CommandScopeManager
from .policy import Flags, ProfileResolver
from .translator import I18nAdapter, build_translator_from_i18n

logger = logging.getLogger(__name__)


async def setup_commands_auto(
    bot: Bot,
    *,
    languages: list[str] | None = None,
    i18n_instance: I18nAdapter | None = None,
    config: CmdsConfig | None = None,
    profile_resolver: ProfileResolver | None = None,
) -> CommandScopeManager:
    """
    Automatically set up command management with minimal configuration.

    This function provides a simple way to set up commands in __main__.py
    with sensible defaults and automatic i18n integration.

    Args:
        bot: Telegram Bot instance
        languages: List of supported languages (default: ["en"])
        i18n_instance: aiogram i18n instance (optional, will try to import from common locations)
        config: Custom CmdsConfig (optional, will create default if not provided)
        profile_resolver: Custom ProfileResolver (optional, will create default if not provided)

    Returns:
        CommandScopeManager instance ready to use

    Example:
        # In __main__.py
        from aiogram_cmds.auto_setup import setup_commands_auto

        async def on_startup(dp, app_context=None):
            command_manager = await setup_commands_auto(bot)
            # Commands are automatically set up!
    """
    # Default languages
    if languages is None:
        languages = ["en"]

    # Try to get i18n instance if not provided
    if i18n_instance is None:
        i18n_instance = _try_import_i18n()

    # Build translator
    translator = build_translator_from_i18n(i18n_instance) if i18n_instance else None

    # Create default config if not provided
    if config is None:
        config = create_default_config(languages)

    # Create default profile resolver if not provided
    if profile_resolver is None:
        profile_resolver = create_default_profile_resolver()

    # Create and setup command manager
    manager = CommandScopeManager(
        bot,
        config=config,
        translator=translator,
        profile_resolver=profile_resolver,
    )

    # Setup all command scopes and menu button
    await manager.setup_all()

    logger.info(
        f"✅ Command management set up with {len(config.commands)} commands and {len(config.profiles)} profiles"
    )

    return manager


def _try_import_i18n() -> I18nAdapter | None:
    """Try to import i18n from common locations."""
    # Common aiogram i18n import patterns
    import_patterns = [
        "bot.core.i18n.i18n",
        "bot.i18n.i18n",
        "i18n.i18n",
        "bot.core.i18n",
        "bot.i18n",
        "i18n",
    ]

    for pattern in import_patterns:
        try:
            module_parts = pattern.split(".")
            module = __import__(pattern, fromlist=[module_parts[-1]])
            # Try to get the i18n instance
            if hasattr(module, "i18n"):
                return cast(I18nAdapter, module.i18n)
            elif hasattr(module, "gettext"):
                return cast(I18nAdapter, module)
        except ImportError:
            continue

    logger.debug(
        "Could not find i18n instance, commands will use fallback descriptions"
    )
    return None


def create_default_config(languages: list[str]) -> CmdsConfig:
    """
    Create a default configuration with basic commands.

    This provides a sensible starting point for most bots.
    """
    return CmdsConfig(
        languages=languages,
        fallback_language=languages[0] if languages else "en",
        i18n_key_prefix="cmd",
        # Basic commands that most bots need
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "cancel": CommandDef(i18n_key="cancel.desc"),
        },
        # Simple profile structure
        profiles={
            "guest": ProfileDef(include=["start", "help"]),
            "user": ProfileDef(include=["start", "help", "cancel"]),
        },
        # Default scope for all private chats
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
        ],
        # Menu button
        menu_button=MenuButtonDef(mode="commands"),
    )


def create_default_profile_resolver() -> ProfileResolver:
    """
    Create a default profile resolver that maps user flags to profiles.

    This provides a simple guest/user distinction based on registration status.
    """

    def default_resolver(flags: Flags) -> str:
        if flags.is_during_registration or not flags.is_registered:
            return "guest"
        return "user"

    return default_resolver
