#!/usr/bin/env python3
"""
Minimal example bot demonstrating aiogram-sentinel features.

This example shows:
- Complete setup with memory backend
- All middleware features (blocking, auth, debouncing, throttling)
- Decorator usage (@rate_limit, @debounce, @require_registered)
- Resolver and notifier hooks
- Router hooks for membership management
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
    Sentinel,
    SentinelConfig,
    debounce,
    rate_limit,
    require_registered,
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


async def resolve_user(
    event: types.TelegramObject, data: dict[str, Any]
) -> dict[str, Any] | None:
    """Hook for custom user resolution and validation."""
    # Extract user information
    if hasattr(event, "from_user") and getattr(event, "from_user", None):  # type: ignore
        user = event.from_user  # type: ignore

        # Custom validation logic
        if getattr(user, "is_bot", False):  # type: ignore
            logger.info(f"Blocking bot user: {getattr(user, 'id', 0)}")  # type: ignore
            return None  # Veto bot users

        # Check if user is in a custom blacklist
        # (This is just an example - you could check against a database)
        blacklisted_users = {123456789, 987654321}  # Example blacklist
        user_id = getattr(user, "id", 0)  # type: ignore
        if user_id in blacklisted_users:
            logger.info(f"Blocking blacklisted user: {user_id}")
            return None  # Veto blacklisted users

        # Return user context
        return {
            "user_id": user_id,
            "username": getattr(user, "username", None),  # type: ignore
            "first_name": getattr(user, "first_name", None),  # type: ignore
            "last_name": getattr(user, "last_name", None),  # type: ignore
            "is_bot": getattr(user, "is_bot", False),  # type: ignore
            "is_premium": getattr(user, "is_premium", False),  # type: ignore
            "language_code": getattr(user, "language_code", None),  # type: ignore
        }

    return None  # No user info available


async def on_user_blocked(user_id: int, username: str, data: dict[str, Any]) -> None:
    """Hook called when a user is blocked (kicked from bot)."""
    logger.info(f"User blocked: {username} (ID: {user_id})")

    # You can implement custom logic here:
    # - Log to audit system
    # - Send notification to admins
    # - Update user statistics
    # - Clean up user data

    # Example: Log to external system
    try:
        # This would be your custom logging/notification system
        print(
            f"🔴 BLOCKED: {username} (ID: {user_id}) - {data.get('old_status')} -> {data.get('new_status')}"
        )
    except Exception as e:
        logger.error(f"Failed to process block event: {e}")


async def on_user_unblocked(user_id: int, username: str, data: dict[str, Any]) -> None:
    """Hook called when a user is unblocked (rejoins bot)."""
    logger.info(f"User unblocked: {username} (ID: {user_id})")

    # You can implement custom logic here:
    # - Send welcome back message
    # - Update user statistics
    # - Restore user preferences
    # - Log to audit system

    # Example: Send welcome back message
    try:
        # This would be your custom notification system
        print(
            f"🟢 UNBLOCKED: {username} (ID: {user_id}) - {data.get('old_status')} -> {data.get('new_status')}"
        )
    except Exception as e:
        logger.error(f"Failed to process unblock event: {e}")


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
        "• Debouncing (1 second delay)\n"
        "• User authentication\n"
        "• Blocking protection\n\n"
        "Try these commands:\n"
        "/start - This message\n"
        "/protected - Requires registration\n"
        "/spam - Test rate limiting\n"
        "/help - Show help"
    )


@require_registered()  # Requires user to be registered
async def protected_handler(message: Message) -> None:
    """Protected handler that requires user registration."""
    await message.answer(
        "🔒 This is a protected command!\n\n"
        "You can only access this if you're registered in the system. "
        "The @require_registered decorator ensures this."
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
        "• Blocking middleware - blocks problematic users\n"
        "• Auth middleware - manages user registration\n"
        "• Debouncing middleware - prevents duplicate messages\n"
        "• Throttling middleware - rate limits requests\n"
        "• Membership router - handles bot membership changes\n\n"
        "**Commands:**\n"
        "/start - Welcome message (rate limited)\n"
        "/protected - Requires registration\n"
        "/spam - Test rate limiting\n"
        "/help - This help message\n\n"
        "**Hooks in action:**\n"
        "• Rate limit notifications\n"
        "• User resolution and validation\n"
        "• Block/unblock event handling"
    )


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

    # Setup aiogram-sentinel (simplified)
    router, backends = await Sentinel.setup(dp, config)

    # Add hooks for advanced functionality
    Sentinel.add_hooks(
        router,
        backends,
        config,
        on_rate_limited=on_rate_limited,
        resolve_user=resolve_user,
        on_block=on_user_blocked,
        on_unblock=on_user_unblocked,
    )

    # Register handlers
    dp.message.register(start_handler, Command("start"))
    dp.message.register(protected_handler, Command("protected"))
    dp.message.register(spam_handler, Command("spam"))
    dp.message.register(help_handler, Command("help"))
    dp.callback_query.register(callback_handler)

    # Log startup information
    logger.info("🚀 Starting aiogram-sentinel example bot...")
    logger.info(f"📊 Backend: {config.backend}")
    logger.info(
        f"⚙️  Rate limit: {config.throttling_default_max}/{config.throttling_default_per_seconds}s"
    )
    logger.info(f"🔄 Debounce window: {config.debounce_default_window}s")
    logger.info("🎯 Hooks enabled: rate_limited, resolve_user, on_block, on_unblock")

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
