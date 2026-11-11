# Basic Setup Tutorial

This tutorial will walk you through setting up aiogram-cmds for your first Telegram bot. We'll create a simple bot with basic command management.

## 🎯 What We'll Build

A simple bot with:
- `/start` and `/help` commands
- Automatic command setup
- Basic user interaction

## 📋 Prerequisites

- Python 3.10+
- aiogram 3.x
- Basic understanding of Python async/await

## 🚀 Step 1: Installation

```bash
pip install aiogram-cmds
```

## 🚀 Step 2: Basic Bot Setup

Create a new file `bot.py`:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram_cmds.auto_setup import setup_commands_auto

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token (replace with your actual token)
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Create bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Global variable to store command manager
command_manager = None

async def on_startup():
    """Called when bot starts up."""
    global command_manager
    
    # Set up commands automatically
    command_manager = await setup_commands_auto(bot)
    logger.info("✅ Bot started and commands set up!")

async def on_shutdown():
    """Called when bot shuts down."""
    logger.info("👋 Bot shutting down...")

# Message handlers
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    """Handle /start command."""
    await message.answer(
        "👋 Welcome to my bot!\n\n"
        "Use /help to see available commands."
    )

@dp.message(Command("help"))
async def handle_help(message: types.Message):
    """Handle /help command."""
    await message.answer(
        "📋 Available commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show this help message"
    )

@dp.message()
async def handle_other_messages(message: types.Message):
    """Handle all other messages."""
    await message.answer(
        "🤔 I don't understand that message.\n"
        "Use /help to see available commands."
    )

async def main():
    """Main function."""
    # Set up startup and shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🚀 Step 3: Run Your Bot

```bash
python bot.py
```

You should see:
```
INFO:__main__:✅ Bot started and commands set up!
```

## 🎉 What Just Happened?

1. **Auto-Setup**: `setup_commands_auto()` automatically configured:
   - `/start` and `/help` commands
   - Commands menu button
   - Default command descriptions

2. **Command Handlers**: Your bot now responds to:
   - `/start` - Shows welcome message
   - `/help` - Shows available commands
   - Any other message - Shows help prompt

3. **Telegram Integration**: Commands appear in the Telegram menu and are available to all users.

## 🔧 Step 4: Customize Commands

Let's add more commands and customize the setup:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram_cmds import CommandScopeManager, CmdsConfig, CommandDef, ProfileDef, ScopeDef, MenuButtonDef

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def on_startup():
    """Set up commands with custom configuration."""
    
    # Define custom configuration
    config = CmdsConfig(
        languages=["en"],
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "about": CommandDef(i18n_key="about.desc"),
            "contact": CommandDef(i18n_key="contact.desc"),
        },
        profiles={
            "default": ProfileDef(include=["start", "help", "about", "contact"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="default"),
        ],
        menu_button=MenuButtonDef(mode="commands"),
    )
    
    # Create manager with custom configuration
    manager = CommandScopeManager(bot, config=config)
    await manager.setup_all()
    
    logger.info("✅ Bot started with custom commands!")

# Message handlers
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    await message.answer(
        "👋 Welcome to my bot!\n\n"
        "Use /help to see available commands."
    )

@dp.message(Command("help"))
async def handle_help(message: types.Message):
    await message.answer(
        "📋 Available commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/about - About this bot\n"
        "/contact - Contact information"
    )

@dp.message(Command("about"))
async def handle_about(message: types.Message):
    await message.answer(
        "ℹ️ About this bot:\n\n"
        "This is a simple bot built with aiogram-cmds.\n"
        "It demonstrates basic command management."
    )

@dp.message(Command("contact"))
async def handle_contact(message: types.Message):
    await message.answer(
        "📞 Contact information:\n\n"
        "Email: bot@example.com\n"
        "GitHub: https://github.com/example/bot"
    )

@dp.message()
async def handle_other_messages(message: types.Message):
    await message.answer(
        "🤔 I don't understand that message.\n"
        "Use /help to see available commands."
    )

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🌍 Step 5: Add i18n Support

Let's add multiple languages to our bot:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram_cmds import CommandScopeManager, CmdsConfig, CommandDef, ProfileDef, ScopeDef
from aiogram_cmds import build_translator_from_i18n

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Simple translator (in real apps, use aiogram i18n)
def simple_translator(key: str, *, locale: str) -> str:
    translations = {
        "en": {
            "cmd.start.desc": "Start the bot",
            "cmd.help.desc": "Show help information",
            "cmd.about.desc": "About this bot",
        },
        "ru": {
            "cmd.start.desc": "Запустить бота",
            "cmd.help.desc": "Показать справку",
            "cmd.about.desc": "О боте",
        },
        "es": {
            "cmd.start.desc": "Iniciar el bot",
            "cmd.help.desc": "Mostrar ayuda",
            "cmd.about.desc": "Acerca del bot",
        },
    }
    return translations.get(locale, {}).get(key)

async def on_startup():
    """Set up commands with i18n support."""
    
    config = CmdsConfig(
        languages=["en", "ru", "es"],
        fallback_language="en",
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "about": CommandDef(i18n_key="about.desc"),
        },
        profiles={
            "default": ProfileDef(include=["start", "help", "about"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="default"),
        ],
    )
    
    manager = CommandScopeManager(
        bot, 
        config=config, 
        translator=simple_translator
    )
    await manager.setup_all()
    
    logger.info("✅ Bot started with i18n support!")

# Message handlers
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    await message.answer("👋 Welcome to my bot!")

@dp.message(Command("help"))
async def handle_help(message: types.Message):
    await message.answer("📋 Use /start to begin!")

@dp.message(Command("about"))
async def handle_about(message: types.Message):
    await message.answer("ℹ️ This is a multi-language bot!")

@dp.message()
async def handle_other_messages(message: types.Message):
    await message.answer("🤔 Use /help for available commands.")

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🎯 Step 6: Test Your Bot

1. **Start your bot**: `python bot.py`
2. **Open Telegram** and find your bot
3. **Test commands**:
   - Send `/start`
   - Send `/help`
   - Send `/about`
   - Try other messages

4. **Check command menu**: Tap the menu button (☰) to see your commands

## 🔧 Step 7: Configuration File

Create `pyproject.toml` for persistent configuration:

```toml
[tool.aiogram_cmds]
languages = ["en", "ru", "es"]
fallback_language = "en"
i18n_key_prefix = "cmd"
profile = "default"
menu_button = "commands"
```

Then use it in your bot:

```python
from aiogram_cmds import load_settings

async def on_startup():
    # Load settings from pyproject.toml
    settings = load_settings()
    
    manager = CommandScopeManager(bot, settings=settings)
    await manager.setup_all()
```

## 🚨 Common Issues

### Commands Not Appearing
- Make sure you call `await manager.setup_all()`
- Check that your bot token is valid
- Verify command names are valid (lowercase, letters, numbers, underscores only)

### Import Errors
```bash
# Make sure aiogram-cmds is installed
pip install aiogram-cmds

# Check installation
python -c "import aiogram_cmds; print(aiogram_cmds.__version__)"
```

### Bot Not Responding
- Check your bot token
- Make sure the bot is running
- Check logs for error messages

## 🎉 Next Steps

Congratulations! You've successfully set up aiogram-cmds. Here's what you can do next:

1. **[i18n Integration Tutorial](i18n-integration.md)** - Learn advanced i18n setup
2. **[Advanced Profiles Tutorial](advanced-profiles.md)** - Create user-specific commands
3. **[Dynamic Commands Tutorial](dynamic-commands.md)** - Update commands at runtime
4. **[Examples](https://github.com/ArmanAvanesyan/aiogram-cmds/tree/main/examples)** - See complete working bots
5. **[API Reference](../api/core.md)** - Explore advanced features

## 💡 Tips

- Start with auto-setup, then customize as needed
- Use configuration files for persistent settings
- Test your bot thoroughly before deploying
- Check the logs for helpful debugging information
- Use the command menu in Telegram to verify your commands

---

**Ready for more?** Check out the [i18n Integration Tutorial](i18n-integration.md) to add multiple languages to your bot!
