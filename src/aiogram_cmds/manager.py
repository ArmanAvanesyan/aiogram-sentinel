"""
High-level manager that supports:
1) Simple mode (CmdsSettings + CommandPolicy -> list of command names)
2) Full customizable mode (CmdsConfig + ProfileResolver -> profiles & scopes)

Use whichever you provide. If both are provided, config mode is used for setup_all(),
and update_user_commands() will prefer the profile resolver if present; otherwise falls
back to policy-based names.
"""

import logging
from typing import TYPE_CHECKING

from aiogram import Bot

from .apply import apply_config
from .dynamic import set_user_profile
from .policy import CommandPolicy, Flags, ProfileResolver, default_policy
from .setters import (
    set_user_commands_by_flags,
    setup_all_command_scopes,
)
from .settings import CmdsSettings
from .translator import Translator

if TYPE_CHECKING:
    from .customize import CmdsConfig

logger = logging.getLogger(__name__)


class CommandScopeManager:
    def __init__(
        self,
        bot: Bot,
        *,
        settings: CmdsSettings | None = None,
        config: "CmdsConfig | None" = None,
        translator: Translator | None = None,
        policy: CommandPolicy | None = None,
        profile_resolver: ProfileResolver | None = None,
        best_effort: bool = False,
    ) -> None:
        if type(best_effort) is not bool:
            raise TypeError("best_effort must be a boolean")
        self.best_effort = best_effort
        self.bot = bot
        self.settings = settings or CmdsSettings()
        self.config = config
        self.translator = translator
        self.policy = policy or default_policy
        self.profile_resolver = profile_resolver

    async def update_user_commands(
        self,
        user_id: int,
        is_registered: bool,
        has_vehicle: bool,
        is_during_registration: bool = False,
        user_language: str = "en",
        chat_id: int | None = None,
    ) -> bool:
        """Apply legacy flag-based selection; failures propagate unless best_effort."""
        flags = Flags(
            is_registered=is_registered,
            has_vehicle=has_vehicle,
            is_during_registration=is_during_registration,
        )

        try:
            if self.config and self.profile_resolver:
                profile = self.profile_resolver(flags)
                await set_user_profile(
                    self.bot,
                    self.config,
                    translator=self.translator,
                    user_id=user_id,
                    chat_id=chat_id,
                    profile=profile,
                    language=user_language,
                )
            else:
                # Classic mode: compute names via policy
                await set_user_commands_by_flags(
                    self.bot,
                    user_id,
                    is_registered=is_registered,
                    has_vehicle=has_vehicle,
                    is_during_registration=is_during_registration,
                    user_language=user_language,
                    policy=self.policy,
                    translator=self.translator,
                    key_prefix=self.settings.i18n_key_prefix,
                )
        except Exception as e:
            logger.error(
                "Failed to update user commands for user %d: %s",
                user_id,
                e,
                exc_info=True,
            )
            if not self.best_effort:
                raise
            return False

        # Human-friendly log
        if is_during_registration:
            status = "registration"
        elif is_registered and has_vehicle:
            status = "onboarded"
        elif is_registered and not has_vehicle:
            status = "registered_no_vehicle"
        else:
            status = "guest"

        logger.info(
            "Updated commands for user %s: %s (registered=%s, vehicle=%s, during_registration=%s)",
            user_id,
            status,
            is_registered,
            has_vehicle,
            is_during_registration,
        )
        return True

    async def update_profile(
        self,
        user_id: int,
        profile: str,
        *,
        language: str = "en",
        chat_id: int | None = None,
    ) -> bool:
        """Apply an application-selected profile without library-owned domain flags."""
        try:
            if self.config is None:
                raise ValueError("update_profile requires CmdsConfig")
            await set_user_profile(
                self.bot,
                self.config,
                translator=self.translator,
                user_id=user_id,
                chat_id=chat_id,
                profile=profile,
                language=language,
            )
        except Exception:
            logger.exception("Failed to apply command profile for user %s", user_id)
            if not self.best_effort:
                raise
            return False
        logger.info("Updated command profile for user %s", user_id)
        return True

    async def clear_user_commands(self, user_id: int) -> bool:
        from aiogram.types import BotCommandScopeChat

        try:
            await self.bot.delete_my_commands(
                scope=BotCommandScopeChat(chat_id=user_id)
            )
        except Exception as e:
            logger.error(
                "Failed to clear commands for user %d: %s", user_id, e, exc_info=True
            )
            if not self.best_effort:
                raise
            return False
        logger.info("Cleared commands for user %s", user_id)
        return True

    async def setup_all(self) -> bool:
        """
        Setup all command scopes + menu button.
        - If a full CmdsConfig is provided: apply_config (full customizable mode)
        - Else: setup_all_command_scopes (classic mode)
        """
        try:
            if self.config:
                await apply_config(self.bot, self.config, translator=self.translator)
            else:
                await setup_all_command_scopes(
                    self.bot,
                    languages=tuple(self.settings.languages),
                    translator=self.translator,
                    key_prefix=self.settings.i18n_key_prefix,
                    menu_button=self.settings.menu_button,
                )
        except Exception as e:
            logger.error("Failed to setup all commands: %s", e, exc_info=True)
            if not self.best_effort:
                raise
            return False
        logger.info("Configured command scopes and menu button")
        return True
