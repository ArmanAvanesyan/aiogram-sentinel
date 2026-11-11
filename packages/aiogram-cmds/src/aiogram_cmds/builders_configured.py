"""
Command builders for config-driven mode.
"""

import logging

from aiogram.types import BotCommand

from .builder import validate_name
from .registry import CommandRegistry
from .translator import Translator

logger = logging.getLogger(__name__)


def build_from_config(
    reg: CommandRegistry,
    names: list[str],
    *,
    lang: str,
    translator: Translator | None,
    key_prefix: str,
) -> list[BotCommand]:
    """
    Build commands using CmdsConfig registry:
    - inline descriptions win
    - else use command.i18n_key (relative to prefix unless dotted)
    - else fallback to {prefix}.{name}.desc
    - else Title Case fallback
    """
    items: list[BotCommand] = []
    for raw in names:
        name = validate_name(raw)
        desc = None
        c = reg.get_command(name)

        # 1) inline descriptions
        if c and c.descriptions:
            desc = c.descriptions.get(lang)

        # 2) specified i18n key
        if not desc and c and c.i18n_key and translator:
            i18n_key = c.i18n_key if "." in c.i18n_key else f"{key_prefix}.{c.i18n_key}"
            try:
                desc = translator(i18n_key, locale=lang)
            except Exception:
                logger.debug(
                    "Translator failed for key %s (lang=%s)",
                    i18n_key,
                    lang,
                    exc_info=True,
                )

        # 3) default i18n key {prefix}.{name}.desc
        if not desc and translator:
            key = f"{key_prefix}.{name}.desc"
            try:
                desc = translator(key, locale=lang)
            except Exception:
                logger.debug(
                    "Translator failed for key %s (lang=%s)", key, lang, exc_info=True
                )

        # 4) fallback
        if not desc:
            desc = name.replace("_", " ").title()

        items.append(BotCommand(command=name[:32], description=desc[:256]))
    return items
