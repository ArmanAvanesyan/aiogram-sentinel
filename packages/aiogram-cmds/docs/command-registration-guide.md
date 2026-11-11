# Command Registration Guide

This guide covers how to register commands, set up automatically, pass locales, and update commands in handlers/scenes using aiogram-cmds with i18n integration.

## Table of Contents

1. [Basic Setup](#basic-setup)
2. [Automatic Setup](#automatic-setup)
3. [Manual Configuration](#manual-configuration)
4. [Dynamic Updates in Handlers](#dynamic-updates-in-handlers)
5. [Scene Integration](#scene-integration)
6. [Locale Management](#locale-management)
7. [Best Practices](#best-practices)

## Basic Setup

### 1. Initialize I18n and Middleware

```python
from aiogram import Bot, Dispatcher
from aiogram.utils.i18n import I18n, SimpleI18nMiddleware
from aiogram_cmds import build_translator_from_i18n

# Create bot and dispatcher
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# Set up i18n
i18n = I18n(path="locales", default_locale="en", domain="messages")
dp.message.middleware(SimpleI18nMiddleware(i18n))

# Create translator for aiogram-cmds
translator = build_translator_from_i18n(i18n)
```

### 2. Create Translation Files

Create `locales/en/LC_MESSAGES/messages.po`:

```po
msgid "cmd.start.desc"
msgstr "Start the bot"

msgid "cmd.help.desc"
msgstr "Show help information"

msgid "cmd.settings.desc"
msgstr "Bot settings"

msgid "cmd.language.desc"
msgstr "Change language"
```

## Automatic Setup

### Using `setup_commands_auto` (Recommended)

The easiest way to set up commands with i18n:

```python
from aiogram_cmds.auto_setup import setup_commands_auto

async def on_startup():
    # Automatic setup with i18n integration
    command_manager = await setup_commands_auto(
        bot,
        languages=["en", "ru", "es"],
        i18n_instance=i18n  # Pass your i18n instance
    )
    
    # Commands are automatically registered for all languages!
    logger.info("✅ Commands set up automatically")

# Register startup handler
dp.startup.register(on_startup)
```

### Custom Auto Setup

```python
from aiogram_cmds import CmdsConfig, CommandDef, ProfileDef, ScopeDef, MenuButtonDef
from aiogram_cmds.auto_setup import setup_commands_auto

async def on_startup():
    # Define your command configuration
    config = CmdsConfig(
        languages=["en", "ru", "es"],
        fallback_language="en",
        i18n_key_prefix="cmd",
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "settings": CommandDef(i18n_key="settings.desc"),
            "language": CommandDef(i18n_key="language.desc"),
        },
        profiles={
            "guest": ProfileDef(include=["start", "help"]),
            "user": ProfileDef(include=["start", "help", "settings", "language"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
        ],
        menu_button=MenuButtonDef(mode="commands"),
    )
    
    # Auto setup with custom config
    command_manager = await setup_commands_auto(
        bot,
        config=config,
        i18n_instance=i18n
    )
```

## Manual Configuration

### Using CommandScopeManager

```python
from aiogram_cmds import CommandScopeManager, CmdsConfig, CommandDef, ProfileDef, ScopeDef

async def on_startup():
    # Create configuration
    config = CmdsConfig(
        languages=["en", "ru", "es"],
        fallback_language="en",
        i18n_key_prefix="cmd",
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "settings": CommandDef(i18n_key="settings.desc"),
        },
        profiles={
            "default": ProfileDef(include=["start", "help", "settings"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="default"),
        ],
    )
    
    # Create manager
    manager = CommandScopeManager(
        bot,
        config=config,
        translator=translator
    )
    
    # Setup all command scopes
    await manager.setup_all()
```

## Dynamic Updates in Handlers

### Update Commands Based on User State

```python
from aiogram import F, types
from aiogram.filters import Command

@dp.message(Command("start"))
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    
    # Update user commands based on registration status
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=True,  # User is now registered
        has_vehicle=False,
        is_during_registration=False,
        user_language=message.from_user.language_code or "en"
    )
    
    await message.answer("Welcome! Your commands have been updated.")

@dp.message(Command("register"))
async def handle_register(message: types.Message):
    user_id = message.from_user.id
    
    # Set user as during registration
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=False,
        has_vehicle=False,
        is_during_registration=True,  # Show registration-specific commands
        user_language=message.from_user.language_code or "en"
    )
    
    await message.answer("Registration started. Use /cancel to stop.")
```

### Language Change Handler

```python
@dp.callback_query(F.data.startswith("lang_"))
async def handle_language_change(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    new_language = callback.data.split("_")[1]  # Extract language code
    
    # Update user's language in i18n
    await i18n.set_locale(user_id, new_language)
    
    # Update user commands with new language
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=True,
        has_vehicle=False,
        is_during_registration=False,
        user_language=new_language  # Pass new language
    )
    
    await callback.message.edit_text(f"Language changed to {new_language}")
```

### Profile-Based Command Updates

```python
# Custom profile resolver
def my_profile_resolver(flags):
    if flags.is_during_registration:
        return "registration"
    elif flags.is_registered and flags.has_vehicle:
        return "premium"
    elif flags.is_registered:
        return "user"
    else:
        return "guest"

# In your handler
@dp.message(Command("upgrade"))
async def handle_upgrade(message: types.Message):
    user_id = message.from_user.id
    
    # User upgraded to premium
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=True,
        has_vehicle=True,  # User now has vehicle (premium feature)
        is_during_registration=False,
        user_language=message.from_user.language_code or "en"
    )
    
    await message.answer("Upgraded to premium! New commands available.")
```

## Scene Integration

### With aiogram FSM

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_phone = State()

@dp.message(Command("register"))
async def start_registration(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Update commands for registration flow
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=False,
        has_vehicle=False,
        is_during_registration=True,  # Show /cancel command
        user_language=message.from_user.language_code or "en"
    )
    
    await state.set_state(RegistrationStates.waiting_name)
    await message.answer("What's your name?")

@dp.message(RegistrationStates.waiting_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(RegistrationStates.waiting_phone)
    await message.answer("What's your phone number?")

@dp.message(RegistrationStates.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    # Registration completed
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=True,  # User is now registered
        has_vehicle=False,
        is_during_registration=False,
        user_language=message.from_user.language_code or "en"
    )
    
    await state.clear()
    await message.answer(f"Welcome, {data['name']}! Registration completed.")

@dp.message(Command("cancel"))
async def cancel_registration(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Reset to guest commands
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=False,
        has_vehicle=False,
        is_during_registration=False,
        user_language=message.from_user.language_code or "en"
    )
    
    await state.clear()
    await message.answer("Registration cancelled.")
```

### With aiogram-dialog

```python
from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.text import Const
from aiogram_dialog.widgets.kbd import Button

# In your dialog
async def on_dialog_start(start_data, manager):
    user_id = start_data["user_id"]
    
    # Update commands when dialog starts
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=True,
        has_vehicle=False,
        is_during_registration=False,
        user_language=start_data.get("language", "en")
    )

# Dialog definition
dialog = Dialog(
    Window(
        Const("Settings dialog"),
        Button(Const("Close"), id="close"),
        state=SettingsState.main,
        getter=on_dialog_start
    )
)
```

## Locale Management

### Getting Current Locale

```python
from aiogram.utils.i18n import gettext as _

@dp.message(Command("info"))
async def handle_info(message: types.Message):
    # Get current locale from context
    current_locale = i18n.current_locale
    
    # Or get user's locale
    user_locale = await i18n.get_locale(message.from_user.id)
    
    await message.answer(f"Current locale: {user_locale}")
```

### Setting Locale Programmatically

```python
@dp.message(Command("setlang"))
async def set_language(message: types.Message):
    user_id = message.from_user.id
    new_lang = message.text.split()[1] if len(message.text.split()) > 1 else "en"
    
    # Set locale
    await i18n.set_locale(user_id, new_lang)
    
    # Update commands with new locale
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=True,
        has_vehicle=False,
        is_during_registration=False,
        user_language=new_lang
    )
    
    await message.answer(f"Language set to {new_lang}")
```

### Pluralization Support

```python
# In your translation files (messages.po)
msgid "{n} file"
msgid_plural "{n} files"
msgstr[0] "{n} файл"
msgstr[1] "{n} файла"
msgstr[2] "{n} файлов"

# In your code
@dp.message(Command("files"))
async def handle_files(message: types.Message):
    file_count = 5
    
    # Use pluralization
    text = translator(
        "{n} file",
        plural="{n} files", 
        count=file_count,
        locale=message.from_user.language_code or "en"
    )
    
    await message.answer(text.format(n=file_count))
```

## Best Practices

### 1. Initialize Commands Early

```python
async def on_startup():
    # Set up commands before starting polling
    global command_manager
    command_manager = await setup_commands_auto(bot, i18n_instance=i18n)
    
    # Set default commands for new users
    await command_manager.setup_all()

dp.startup.register(on_startup)
```

### 2. Handle Errors Gracefully

```python
async def safe_update_commands(user_id: int, **kwargs):
    try:
        await command_manager.update_user_commands(
            user_id=user_id,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Failed to update commands for user {user_id}: {e}")
        # Continue without crashing

# Usage
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    await safe_update_commands(
        message.from_user.id,
        is_registered=True,
        has_vehicle=False,
        user_language=message.from_user.language_code or "en"
    )
```

### 3. Cache Command Manager

```python
# In your main module
command_manager = None

async def get_command_manager():
    global command_manager
    if command_manager is None:
        command_manager = await setup_commands_auto(bot, i18n_instance=i18n)
    return command_manager

# In handlers
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    manager = await get_command_manager()
    await manager.update_user_commands(...)
```

### 4. Use Context Variables

```python
from contextvars import ContextVar

# Define context variable
current_user_locale: ContextVar[str] = ContextVar('current_user_locale', default='en')

# In middleware or handler
@dp.message()
async def set_locale_context(message: types.Message):
    locale = message.from_user.language_code or "en"
    current_user_locale.set(locale)
    
    # Now translator will use this locale automatically
    text = translator("welcome.message")  # No need to pass locale
```

### 5. Batch Command Updates

```python
async def update_multiple_users(user_ids: list[int], **kwargs):
    """Update commands for multiple users efficiently."""
    tasks = []
    for user_id in user_ids:
        task = command_manager.update_user_commands(user_id=user_id, **kwargs)
        tasks.append(task)
    
    await asyncio.gather(*tasks, return_exceptions=True)
```

## Complete Example

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.i18n import I18n, SimpleI18nMiddleware
from aiogram_cmds.auto_setup import setup_commands_auto

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot setup
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

# I18n setup
i18n = I18n(path="locales", default_locale="en", domain="messages")
dp.message.middleware(SimpleI18nMiddleware(i18n))

# Global command manager
command_manager = None

async def on_startup():
    global command_manager
    command_manager = await setup_commands_auto(
        bot,
        languages=["en", "ru", "es"],
        i18n_instance=i18n
    )
    logger.info("✅ Bot started with command management")

@dp.message(Command("start"))
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    
    # Update commands for new user
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=True,
        has_vehicle=False,
        is_during_registration=False,
        user_language=message.from_user.language_code or "en"
    )
    
    await message.answer("Welcome! Commands updated.")

@dp.callback_query(F.data.startswith("lang_"))
async def handle_language_change(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    new_lang = callback.data.split("_")[1]
    
    # Update locale and commands
    await i18n.set_locale(user_id, new_lang)
    await command_manager.update_user_commands(
        user_id=user_id,
        is_registered=True,
        has_vehicle=False,
        is_during_registration=False,
        user_language=new_lang
    )
    
    await callback.message.edit_text(f"Language changed to {new_lang}")

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

This guide covers all aspects of command registration, automatic setup, locale management, and dynamic updates in handlers and scenes. The key is to use the `setup_commands_auto` function for easy setup and `update_user_commands` for dynamic updates based on user state changes.
