#!/usr/bin/env python3
"""
Minimal example bot demonstrating aiogram-sentinel features.

This example shows:
- Complete setup with memory backend
- Rate limiting and debouncing middleware
- Error handling with friendly messages
- Decorator usage (@rate_limit, @debounce)
- Rate limit hooks
- Custom hook implementations

Run with: python examples/minimal_bot.py
Make sure to set your BOT_TOKEN environment variable.
"""

import asyncio
import logging
import os
from typing import Any

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

# Import aiogram-sentinel
from aiogram_sentinel import (
    ErrorConfig,
    Sentinel,
    SentinelConfig,
    debounce,
    rate_limit,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# HOOK IMPLEMENTATIONS
# ============================================================================


async def on_rate_limited(
    event: types.TelegramObject, data: dict[str, Any], retry_after: float
) -> None:
    """Hook called when a user is rate limited."""
    logger.info(f"Rate limit exceeded for user. Retry after {retry_after:.1f}s")

    # You can implement custom logic here:
    # - Send a warning message to the user
    # - Log to external monitoring
    # - Update user statistics
    # - Send notification to admins

    if isinstance(event, Message):
        try:
            await event.answer(
                f"⏰ You're sending messages too quickly. Please wait {retry_after:.1f} seconds.",
                show_alert=True,
            )
        except Exception as e:
            logger.error(f"Failed to send rate limit message: {e}")


# ============================================================================
# ERROR HANDLING CONFIGURATION
# ============================================================================


def classify_domain_error(exc: Exception) -> str | None:
    """Classify domain-specific exceptions."""
    if isinstance(exc, ValueError):
        return "error_validation"
    elif isinstance(exc, PermissionError):
        return "error_permission"
    return None


def resolve_locale(event: types.TelegramObject, data: dict) -> str:
    """Resolve user locale for error messages."""
    user = getattr(event, "from_user", None)
    if user and hasattr(user, "language_code"):
        return user.language_code or "en"
    return "en"


def resolve_message(key: str, locale: str) -> str:
    """Resolve error keys to user-friendly messages."""
    messages = {
        "en": {
            "error_validation": "Please check your input and try again.",
            "error_permission": "You do not have permission to perform this action.",
            "error_telegram_badrequest": "Invalid request. Please try again.",
            "error_telegram_forbidden": "Access denied.",
            "error_telegram_retry_after": "Please wait a moment and try again.",
            "error_unexpected_system": "An unexpected error occurred. Please try again later.",
        }
    }
    return messages.get(locale, messages["en"]).get(key, key)


async def on_error(event: types.TelegramObject, exc: Exception, data: dict) -> None:
    """Custom error handler for logging and monitoring."""
    logger.exception(f"Handler error: {exc}")
    # Here you could send error reports to monitoring systems


# Configure error handling
error_config = ErrorConfig(
    use_friendly_messages=True,
    domain_classifier=classify_domain_error,
    locale_resolver=resolve_locale,
    message_resolver=resolve_message,
    on_error=on_error,
    show_alert_for_callbacks=True,
)


# ============================================================================
# BOT HANDLERS
# ============================================================================


@rate_limit(3, 30)  # 3 messages per 30 seconds
@debounce(1)  # 1 second debounce
async def start_handler(message: Message) -> None:
    """Start command handler with rate limiting and debouncing."""
    await message.answer(
        "🤖 Welcome to aiogram-sentinel example bot!\n\n"
        "This bot demonstrates:\n"
        "• Rate limiting (3 messages per 30 seconds)\n"
        "• Debouncing (1 second delay)\n\n"
        "Try these commands:\n"
        "/start - This message\n"
        "/spam - Test rate limiting\n"
        "/help - Show help"
    )


@rate_limit(1, 5)  # Very strict rate limit for testing
async def spam_handler(message: Message) -> None:
    """Handler for testing rate limiting."""
    await message.answer(
        "📨 Message received!\n\n"
        "This handler has a strict rate limit: 1 message per 5 seconds. "
        "Try sending multiple messages quickly to see rate limiting in action."
    )


async def help_handler(message: Message) -> None:
    """Help command handler."""
    await message.answer(
        "📚 aiogram-sentinel Example Bot\n\n"
        "**Features demonstrated:**\n"
        "• Debouncing middleware - prevents duplicate messages\n"
        "• Throttling middleware - rate limits requests\n"
        "• Error handling - friendly error messages\n\n"
        "**Commands:**\n"
        "/start - Welcome message (rate limited)\n"
        "/spam - Test rate limiting\n"
        "/error - Test error handling\n"
        "/help - This help message\n\n"
        "**Hooks in action:**\n"
        "• Rate limit notifications"
    )


async def error_handler(message: Message) -> None:
    """Handler that demonstrates error handling."""
    # This will raise a ValueError, which will be caught by the error middleware
    # and converted to a friendly message
    raise ValueError("This is a test error to demonstrate error handling")


async def callback_handler(callback: CallbackQuery) -> None:
    """Callback query handler."""
    await callback.answer("Callback received!")
    if callback.message:  # type: ignore
        await callback.message.edit_text("✅ Callback processed successfully!")  # type: ignore


# ============================================================================
# BOT SETUP AND RUN
# ============================================================================


async def main() -> None:
    """Main function to run the bot."""
    # Get bot token from environment
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN environment variable is required!")
        return

    # Create bot and dispatcher
    bot = Bot(token=bot_token)
    dp = Dispatcher()

    # Configure aiogram-sentinel
    config = SentinelConfig(
        backend="memory",  # Use memory backend for simplicity
        throttling_default_max=5,  # Default: 5 messages per window
        throttling_default_per_seconds=60,  # Default: 60 second window
        debounce_default_window=2,  # Default: 2 second debounce
    )

    # Setup aiogram-sentinel with error handling
    router, infra = await Sentinel.setup(dp, config, error_config=error_config)

    # Add hooks for advanced functionality
    Sentinel.add_hooks(
        router,
        infra,
        config,
        on_rate_limited=on_rate_limited,
    )

    # Register handlers
    dp.message.register(start_handler, Command("start"))
    dp.message.register(spam_handler, Command("spam"))
    dp.message.register(error_handler, Command("error"))
    dp.message.register(help_handler, Command("help"))
    dp.callback_query.register(callback_handler)

    # Log startup information
    logger.info("🚀 Starting aiogram-sentinel example bot...")
    logger.info(f"📊 Backend: {config.backend}")
    logger.info(
        f"⚙️  Rate limit: {config.throttling_default_max}/{config.throttling_default_per_seconds}s"
    )
    logger.info(f"🔄 Debounce window: {config.debounce_default_window}s")
    logger.info("🎯 Hooks enabled: rate_limited")

    try:
        # Start polling
        await dp.start_polling(bot)  # type: ignore
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    # Check if running directly
    if not os.getenv("BOT_TOKEN"):
        print("❌ Error: BOT_TOKEN environment variable is required!")
        print("Set it with: export BOT_TOKEN='your_bot_token_here'")
        print("Or run with: BOT_TOKEN='your_token' python examples/minimal_bot.py")
        exit(1)

    # Run the bot
    asyncio.run(main())
