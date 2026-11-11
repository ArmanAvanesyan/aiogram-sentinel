#!/usr/bin/env python3
"""Run a protected, process-local bot: BOT_TOKEN=... uv run examples/minimal_bot.py."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject

from aiogram_sentinel import ErrorConfig, Sentinel, SentinelConfig

logger = logging.getLogger(__name__)


async def on_rate_limited(
    event: TelegramObject, data: dict[str, Any], retry_after: float
) -> None:
    """Notify a user without logging message content or credentials."""
    logger.debug("Rate limit reached; retry after %.1fs", retry_after)
    if isinstance(event, Message):
        await event.answer(f"Please wait {retry_after:.1f} seconds and try again.")


def classify_domain_error(exc: Exception) -> str | None:
    """Map application errors to a message key, rather than exposing details."""
    return "validation" if isinstance(exc, ValueError) else None


def resolve_message(key: str, locale: str) -> str:
    """Replace this English resolver with the application's localization layer."""
    if key == "validation":
        return "Please check your input and try again."
    return "An error occurred. Please try again later."


async def start_handler(message: Message) -> None:
    await message.answer(
        "Sentinel memory example. Commands: /start, /spam, /error, /help.\n"
        "Repeated identical messages are suppressed for 2 seconds.\n"
        "Send /spam one and /spam two quickly to exercise the rate-limit hook."
    )


async def spam_handler(message: Message) -> None:
    await message.answer("Message accepted.")


async def error_handler(message: Message) -> None:
    raise ValueError("Demonstration validation failure")


async def help_handler(message: Message) -> None:
    await message.answer("Use /start for instructions or /error for a friendly error.")


async def build_dispatcher() -> Dispatcher:
    """Register handlers on the protected router, not the parent dispatcher."""
    dispatcher = Dispatcher()
    config = SentinelConfig(
        backend="memory",
        throttling_default_max=1,
        throttling_default_per_seconds=5,
        debounce_default_window=2,
    )
    router, infra = await Sentinel.setup(
        dispatcher,
        config,
        error_config=ErrorConfig(
            domain_classifier=classify_domain_error,
            message_resolver=resolve_message,
        ),
    )
    Sentinel.add_hooks(router, infra, config, on_rate_limited=on_rate_limited)
    router.message.register(start_handler, Command("start"))
    router.message.register(spam_handler, Command("spam"))
    router.message.register(error_handler, Command("error"))
    router.message.register(help_handler, Command("help"))
    return dispatcher


async def main() -> None:
    """Configure application logging only when the example is executed."""
    logging.basicConfig(level=logging.INFO)
    logger.setLevel(logging.DEBUG)
    logging.getLogger("aiogram_sentinel").setLevel(logging.DEBUG)
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN before running the example.")
    bot = Bot(token)
    try:
        dispatcher = await build_dispatcher()
        try:
            await dispatcher.start_polling(bot)
        finally:
            await dispatcher.storage.close()
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
