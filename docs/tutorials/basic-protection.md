# Tutorial: Basic Bot Protection

**Goal**: Build a Telegram bot with comprehensive protection against spam and abuse.

**What you'll build**: A bot that handles messages with rate limiting, user blocking, and authentication.

## Prerequisites

- Python 3.10+
- aiogram v3 installed
- A Telegram bot token
- Basic understanding of async/await

## Step 1: Project Setup

Create a new directory and install dependencies:

```bash
mkdir my-protected-bot
cd my-protected-bot
pip install aiogram aiogram-sentinel
```

## Step 2: Basic Bot Structure

Create `bot.py`:

```python
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram_sentinel import Sentinel

# Initialize bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Create Sentinel instance
sentinel = Sentinel()

# Register middleware
dp.message.middleware(sentinel.middleware)

@dp.message()
async def handle_message(message: Message):
    """Handle all messages with protection."""
    await message.answer(f"Hello! Your message: {message.text}")

async def main():
    """Start the bot."""
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Step 3: Test Basic Protection

Run your bot:

```bash
python bot.py
```

Send a few messages to your bot. You should see:
- Messages are processed normally
- Rate limiting prevents spam
- New users are automatically registered

## Step 4: Add Custom Configuration

Modify your bot to use custom protection settings:

```python
from aiogram_sentinel import Sentinel, SentinelConfig

# Create custom configuration
config = SentinelConfig(
    throttling_default_max=3,      # 3 messages
    throttling_default_per_seconds=60,  # per minute
    debounce_default_window=5,     # 5 second debounce
)

# Create Sentinel with custom config
sentinel = Sentinel(config=config)
```

## Step 5: Add User Blocking

Add a command to block/unblock users:

```python
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram_sentinel import Sentinel

# ... existing code ...

@dp.message(Command("block"))
async def block_user(message: Message):
    """Block a user (admin only)."""
    if message.from_user.id != YOUR_ADMIN_ID:  # Replace with your ID
        return
    
    # Extract user ID from reply or command argument
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        try:
            user_id = int(message.text.split()[1])
        except (IndexError, ValueError):
            await message.answer("Usage: /block <user_id> or reply to a message")
            return
    
    # Block the user
    await sentinel.blocklist_backend.set_blocked(user_id, True)
    await message.answer(f"User {user_id} has been blocked")

@dp.message(Command("unblock"))
async def unblock_user(message: Message):
    """Unblock a user (admin only)."""
    if message.from_user.id != YOUR_ADMIN_ID:  # Replace with your ID
        return
    
    # Extract user ID from reply or command argument
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        try:
            user_id = int(message.text.split()[1])
        except (IndexError, ValueError):
            await message.answer("Usage: /unblock <user_id> or reply to a message")
            return
    
    # Unblock the user
    await sentinel.blocklist_backend.set_blocked(user_id, False)
    await message.answer(f"User {user_id} has been unblocked")
```

## Step 6: Add Rate Limit Status

Add a command to check rate limit status:

```python
@dp.message(Command("status"))
async def check_status(message: Message):
    """Check rate limit status."""
    user_id = message.from_user.id
    key = f"user:{user_id}:handler"
    
    # Get current rate limit count
    count = await sentinel.rate_limiter_backend.get_rate_limit(key)
    
    await message.answer(f"Your current rate limit count: {count}")
```

## Step 7: Test All Features

Test your bot with these scenarios:

1. **Normal usage**: Send regular messages
2. **Rate limiting**: Send messages rapidly to trigger rate limiting
3. **User blocking**: Use `/block` and `/unblock` commands
4. **Status check**: Use `/status` to see rate limit information

## Verify Results

Your bot should now:
- ✅ Process messages normally
- ✅ Rate limit users who send too many messages
- ✅ Block/unblock users on command
- ✅ Show rate limit status
- ✅ Automatically register new users

## What's Next?

- [Advanced Configuration Tutorial](advanced-configuration.md)
- [Redis Storage Tutorial](redis-storage.md)
- [Custom Middleware Tutorial](custom-middleware.md)

## Troubleshooting

**Bot not responding**: Check your bot token and ensure the bot is running.

**Rate limiting not working**: Verify the middleware is registered correctly.

**Blocking not working**: Check that you're using the correct user ID format.

**Import errors**: Ensure aiogram-sentinel is installed correctly.
