# Quickstart Guide

Get started with aiogram-cmds in under 5 minutes! This guide will walk you through setting up command management for your Telegram bot.

## 🚀 Installation

```bash
pip install aiogram-cmds
```

## ⚡ Auto-Setup (Recommended)

The fastest way to get started is with auto-setup:

```python
from aiogram import Bot, Dispatcher
from aiogram_cmds.auto_setup import setup_commands_auto

async def on_startup():
    # Automatically set up commands with sensible defaults
    command_manager = await setup_commands_auto(bot)
    print("✅ Commands set up successfully!")

# Your bot handlers
@dp.message(Command("start"))
async def handle_start(message: Message):
    await message.answer("Welcome! Use /help to see available commands.")

@dp.message(Command("help"))
async def handle_help(message: Message):
    await message.answer("Available commands:\n/start - Start the bot\n/help - Show this help")
```

That's it! Your bot now has:
- `/start` and `/help` commands available to all users
- Commands menu button enabled
- Automatic command descriptions

## 🎯 Simple Mode

For more control, use the simple mode:

```python
from aiogram import Bot, Dispatcher
from aiogram_cmds import CommandScopeManager, load_settings

# Load settings (optional - uses defaults if not found)
settings = load_settings()  # Reads from pyproject.toml [tool.aiogram_cmds]

# Create manager
manager = CommandScopeManager(bot, settings=settings)

# Set up all command scopes
await manager.setup_all()

# Update user commands based on their status
await manager.update_user_commands(
    user_id=12345,
    is_registered=True,
    has_vehicle=False,
    user_language="en"
)
```

## 🌍 Adding i18n Support

To add multiple languages:

```python
from aiogram_cmds import build_translator_from_i18n

# Assuming you have an aiogram i18n instance
translator = build_translator_from_i18n(i18n)

manager = CommandScopeManager(
    bot, 
    settings=settings, 
    translator=translator
)
```

Create translation files:

```json
// locales/en.json
{
  "cmd.start.desc": "Start the bot",
  "cmd.help.desc": "Show help information",
  "cmd.profile.desc": "View your profile"
}

// locales/ru.json
{
  "cmd.start.desc": "Запустить бота",
  "cmd.help.desc": "Показать справку",
  "cmd.profile.desc": "Посмотреть профиль"
}
```

## 🎛️ Advanced Mode

For complex scenarios with custom profiles:

```python
from aiogram_cmds import CmdsConfig, CommandDef, ProfileDef, ScopeDef, MenuButtonDef

# Define your command configuration
config = CmdsConfig(
    languages=["en", "ru"],
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "help": CommandDef(i18n_key="help.desc"),
        "profile": CommandDef(i18n_key="profile.desc"),
        "admin": CommandDef(i18n_key="admin.desc"),
    },
    profiles={
        "guest": ProfileDef(include=["start", "help"]),
        "user": ProfileDef(include=["start", "help", "profile"]),
        "admin": ProfileDef(include=["start", "help", "profile", "admin"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="guest"),
        ScopeDef(scope="chat", chat_id=12345, profile="admin"),
    ],
    menu_button=MenuButtonDef(mode="commands"),
)

# Custom profile resolver
def my_profile_resolver(flags):
    if flags.is_admin:
        return "admin"
    elif flags.is_registered:
        return "user"
    return "guest"

manager = CommandScopeManager(
    bot, 
    config=config, 
    profile_resolver=my_profile_resolver
)

await manager.setup_all()
```

## 🔄 Dynamic Command Updates

Update user commands at runtime:

```python
# When user registers
await manager.update_user_commands(
    user_id=user_id,
    is_registered=True,
    has_vehicle=False,
    user_language="en"
)

# When user gets admin privileges
await manager.update_user_commands(
    user_id=user_id,
    is_registered=True,
    has_vehicle=True,
    is_admin=True,  # Custom flag
    user_language="en"
)

# Clear user commands
await manager.clear_user_commands(user_id)
```

## 📝 Configuration File

Create `pyproject.toml` for persistent settings:

```toml
[tool.aiogram_cmds]
languages = ["en", "ru", "es"]
fallback_language = "en"
i18n_key_prefix = "cmd"
profile = "default"
menu_button = "commands"
```

## 🎯 Common Patterns

### E-commerce Bot
```python
profiles = {
    "visitor": ProfileDef(include=["start", "catalog", "help"]),
    "customer": ProfileDef(include=["start", "catalog", "cart", "orders", "help"]),
    "vip": ProfileDef(include=["start", "catalog", "cart", "orders", "vip_offers", "help"]),
}
```

### Admin Bot
```python
scopes = [
    ScopeDef(scope="all_private_chats", profile="user"),
    ScopeDef(scope="chat_member", chat_id=admin_chat_id, user_id=admin_user_id, profile="admin"),
]
```

### Multi-Language Bot
```python
config = CmdsConfig(
    languages=["en", "ru", "es", "fr"],
    commands={
        "start": CommandDef(i18n_key="commands.start"),
        "help": CommandDef(i18n_key="commands.help"),
    }
)
```

## 🚨 Common Issues

### Commands Not Appearing
- Make sure you call `await manager.setup_all()` after creating the manager
- Check that your bot token has the necessary permissions
- Verify command names are valid (lowercase, letters, numbers, underscores only)

### i18n Not Working
- Ensure your i18n instance is properly configured
- Check that translation keys exist in your locale files
- Verify the `i18n_key_prefix` matches your translation key structure

### Profile Resolver Issues
- Make sure your profile resolver returns valid profile names
- Check that profiles are defined in your configuration
- Verify that the profile includes/excludes valid command names

## 🎉 Next Steps

- Check out the [Configuration Guide](configuration.md) for detailed options
- Read the [Architecture](ARCHITECTURE.md) to understand how it works
- Browse [Examples](https://github.com/ArmanAvanesyan/aiogram-cmds/tree/main/examples) for complete working bots
- Explore the [API Reference](api/core.md) for advanced usage

## 💡 Tips

- Start with auto-setup, then move to simple mode as needed
- Use i18n keys for command descriptions to support multiple languages
- Test your profile resolver with different user states
- Use the `clear_user_commands()` method to reset user command overrides
- Check the logs for helpful debugging information

---

**Ready for more?** Check out our [Tutorials](tutorials/basic-setup.md) for step-by-step guides!
