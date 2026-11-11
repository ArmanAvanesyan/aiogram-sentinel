"""
Command building - construct BotCommand objects from names and i18n/inlined descriptions.

- Validates command names per Telegram constraints.
- Resolves descriptions via translator or falls back to Title Case.
- Enforces Telegram length limits (name: 1..32, description: 1..256).
"""

import logging
import re

from aiogram.types import BotCommand

from .translator import Translator

logger = logging.getLogger(__name__)

# Telegram /command rules (lowercase letters, digits, underscores; must start with a letter)
_CMD_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def validate_name(name: str) -> str:
    """Coerce a human/provided name into a safe Telegram command name."""
    n = (name or "").strip().lower().replace(" ", "_")
    if not _CMD_RE.match(n):
        logger.debug("Invalid command name '%s', coercing to safe form", name)
        # drop leading non-letters
        while n and not n[0].isalpha():
            n = n[1:]
        # remove invalid chars
        n = re.sub(r"[^a-z0-9_]", "", n)
        # clamp length
        n = n[:32] if n else "cmd"
        if not _CMD_RE.match(n):
            n = "cmd"
    return n


def build_bot_commands(
    command_names: list[str],
    *,
    lang: str,
    translator: Translator | None = None,
    key_prefix: str = "cmd",
) -> list[BotCommand]:
    """
    Build BotCommand objects from command names using i18n descriptions.

    i18n key pattern by default: {key_prefix}.{name}.desc
    """
    cmds: list[BotCommand] = []

    for raw in command_names:
        name = validate_name(raw)

        # Try to get description from i18n
        desc = None
        if translator:
            key = f"{key_prefix}.{name}.desc"
            try:
                desc = translator(key, locale=lang)
            except Exception:  # pragma: no cover
                logger.debug(
                    "Translator failed for key %s (lang=%s)", key, lang, exc_info=True
                )

        # Fallback if missing translation
        if not desc:
            desc = name.replace("_", " ").title()
            logger.debug(
                "Missing i18n for %s.%s, fallback to '%s'", key_prefix, name, desc
            )

        cmds.append(BotCommand(command=name[:32], description=desc[:256]))

    logger.debug("Built %d commands for language '%s'", len(cmds), lang)
    return cmds
