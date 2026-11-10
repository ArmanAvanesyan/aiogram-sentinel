# Troubleshooting Guide

This guide helps you diagnose and fix common issues with aiogram-cmds.

## 🚨 Common Issues

### Commands Not Appearing in Telegram

**Symptoms:**
- Commands don't show up in the Telegram menu
- Users can't see bot commands
- Commands work when typed manually but not in menu

**Possible Causes:**

1. **Not calling setup_all()**
   ```python
   # ❌ Missing setup
   manager = CommandScopeManager(bot)
   # Commands won't appear
   
   # ✅ Correct
   manager = CommandScopeManager(bot)
   await manager.setup_all()  # This is required!
   ```

2. **Invalid bot token**
   ```python
   # Check your bot token
   bot = Bot(token="YOUR_BOT_TOKEN")  # Make sure this is correct
   ```

3. **Invalid command names**
   ```python
   # ❌ Invalid command names
   commands = {
       "Start Bot": CommandDef(...),  # Spaces not allowed
       "help-me": CommandDef(...),    # Hyphens not allowed
       "123start": CommandDef(...),   # Can't start with number
   }
   
   # ✅ Valid command names
   commands = {
       "start": CommandDef(...),      # Lowercase, letters only
       "help": CommandDef(...),       # Valid
       "start_bot": CommandDef(...),  # Underscores allowed
   }
   ```

4. **Command name too long**
   ```python
   # ❌ Too long (max 32 characters)
   "this_is_a_very_long_command_name_that_exceeds_limit": CommandDef(...)
   
   # ✅ Valid length
   "start": CommandDef(...)
   ```

**Debug Steps:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Check if setup_all() is called
manager = CommandScopeManager(bot)
await manager.setup_all()  # Should log success messages
```

### i18n Translations Not Working

**Symptoms:**
- Commands show fallback descriptions instead of translations
- Translations work in some languages but not others
- Translation keys not found

**Possible Causes:**

1. **Missing translator setup**
   ```python
   # ❌ No translator
   manager = CommandScopeManager(bot)
   
   # ✅ With translator
   translator = build_translator_from_i18n(i18n)
   manager = CommandScopeManager(bot, translator=translator)
   ```

2. **Incorrect translation key pattern**
   ```python
   # Configuration
   config = CmdsConfig(
       i18n_key_prefix="cmd",
       commands={
           "start": CommandDef(i18n_key="start.desc"),
       }
   )
   
   # Translation file should have:
   # cmd.start.desc = "Start the bot"
   ```

3. **Missing translation files**
   ```bash
   # Check if translation files exist
   ls locales/en/LC_MESSAGES/messages.mo
   ls locales/ru/LC_MESSAGES/messages.mo
   ```

4. **Translation files not compiled**
   ```bash
   # Compile translation files
   msgfmt locales/en/LC_MESSAGES/messages.po -o locales/en/LC_MESSAGES/messages.mo
   ```

**Debug Steps:**
```python
# Test translator directly
translator = build_translator_from_i18n(i18n)
result = translator("cmd.start.desc", locale="en")
print(f"Translation result: {result}")

# Check i18n instance
print(f"i18n instance: {i18n}")
print(f"Available locales: {i18n.available_locales}")
```

### Profile Resolver Not Working

**Symptoms:**
- Users get wrong command sets
- Profile changes don't update commands
- All users get the same commands

**Possible Causes:**

1. **Profile resolver not returning valid profiles**
   ```python
   # ❌ Invalid profile name
   def bad_resolver(flags: Flags) -> str:
       return "invalid_profile"  # Not defined in config
   
   # ✅ Valid profile name
   def good_resolver(flags: Flags) -> str:
       return "user"  # Defined in profiles
   ```

2. **Profile not defined in configuration**
   ```python
   # ❌ Profile not defined
   config = CmdsConfig(
       profiles={
           "user": ProfileDef(include=["start", "help"]),
       }
   )
   
   def resolver(flags: Flags) -> str:
       return "admin"  # "admin" profile not defined!
   ```

3. **Not calling update_user_commands()**
   ```python
   # ❌ Profile changed but commands not updated
   user_db[user_id]["premium"] = True
   # Commands still show old profile
   
   # ✅ Update commands after profile change
   user_db[user_id]["premium"] = True
   await manager.update_user_commands(
       user_id=user_id,
       is_registered=True,
       has_vehicle=True
   )
   ```

**Debug Steps:**
```python
# Test profile resolver
def test_resolver(flags: Flags) -> str:
    profile = my_resolver(flags)
    print(f"Flags: {flags}, Profile: {profile}")
    return profile

# Check profile definitions
config = CmdsConfig(...)
print(f"Available profiles: {list(config.profiles.keys())}")
```

### Dynamic Command Updates Not Working

**Symptoms:**
- Commands don't update after user actions
- Users still see old commands
- Profile changes don't reflect in commands

**Possible Causes:**

1. **Not calling update_user_commands()**
   ```python
   # ❌ State changed but commands not updated
   user_state["premium"] = True
   
   # ✅ Update commands after state change
   user_state["premium"] = True
   await manager.update_user_commands(
       user_id=user_id,
       is_registered=True,
       has_vehicle=True
   )
   ```

2. **Profile resolver not using updated state**
   ```python
   # ❌ Resolver uses old state
   def resolver(flags: Flags) -> str:
       # This might use cached or old user data
       return get_profile_from_database(user_id)
   
   # ✅ Resolver uses current state
   def resolver(flags: Flags) -> str:
       user_id = getattr(flags, 'user_id', None)
       current_state = get_current_user_state(user_id)
       return determine_profile(current_state)
   ```

3. **Telegram API rate limits**
   ```python
   # ❌ Too many rapid updates
   for user_id in user_list:
       await manager.update_user_commands(user_id, ...)
   
   # ✅ Batch updates or add delays
   for user_id in user_list:
       await manager.update_user_commands(user_id, ...)
       await asyncio.sleep(0.1)  # Small delay
   ```

**Debug Steps:**
```python
# Log command updates
async def debug_update_commands(user_id: int, **flags):
    print(f"Updating commands for user {user_id} with flags: {flags}")
    await manager.update_user_commands(user_id, **flags)
    print(f"Commands updated for user {user_id}")
```

### Import Errors

**Symptoms:**
- `ModuleNotFoundError: No module named 'aiogram_cmds'`
- Import errors when running the bot
- Version conflicts

**Possible Causes:**

1. **aiogram-cmds not installed**
   ```bash
   # Install aiogram-cmds
   pip install aiogram-cmds
   ```

2. **Wrong Python environment**
   ```bash
   # Check which Python you're using
   which python
   which pip
   
   # Install in the correct environment
   pip install aiogram-cmds
   ```

3. **Version conflicts**
   ```bash
   # Check installed versions
   pip list | grep aiogram
   
   # Update aiogram-cmds
   pip install --upgrade aiogram-cmds
   ```

**Debug Steps:**
```python
# Test import
try:
    import aiogram_cmds
    print(f"aiogram-cmds version: {aiogram_cmds.__version__}")
except ImportError as e:
    print(f"Import error: {e}")
```

### Bot Not Responding

**Symptoms:**
- Bot doesn't respond to messages
- Commands work but bot is silent
- Bot appears offline

**Possible Causes:**

1. **Invalid bot token**
   ```python
   # Check bot token
   bot = Bot(token="YOUR_BOT_TOKEN")
   
   # Test bot
   async def test_bot():
       me = await bot.get_me()
       print(f"Bot info: {me}")
   ```

2. **Bot not running**
   ```python
   # Make sure bot is started
   await dp.start_polling(bot)
   ```

3. **Message handlers not registered**
   ```python
   # ❌ Handler not registered
   async def handle_start(message: Message):
       await message.answer("Hello!")
   
   # ✅ Handler registered
   @dp.message(Command("start"))
   async def handle_start(message: Message):
       await message.answer("Hello!")
   ```

4. **Middleware blocking messages**
   ```python
   # Check middleware
   print(f"Middleware: {dp.message.middleware}")
   ```

**Debug Steps:**
```python
# Test bot connection
async def test_connection():
    try:
        me = await bot.get_me()
        print(f"Bot connected: {me.username}")
    except Exception as e:
        print(f"Connection error: {e}")

# Test message handling
@dp.message()
async def debug_handler(message: Message):
    print(f"Received message: {message.text}")
    await message.answer("Bot is working!")
```

## 🔧 Debugging Tools

### Enable Debug Logging

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Or for specific loggers
logging.getLogger("aiogram_cmds").setLevel(logging.DEBUG)
logging.getLogger("aiogram").setLevel(logging.DEBUG)
```

### Test Configuration

```python
def test_configuration():
    """Test your configuration."""
    try:
        config = CmdsConfig(
            languages=["en", "ru"],
            commands={
                "start": CommandDef(i18n_key="start.desc"),
                "help": CommandDef(i18n_key="help.desc"),
            },
            profiles={
                "user": ProfileDef(include=["start", "help"]),
            },
            scopes=[
                ScopeDef(scope="all_private_chats", profile="user"),
            ],
        )
        print("✅ Configuration is valid")
        return config
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return None
```

### Test Profile Resolver

```python
def test_profile_resolver():
    """Test your profile resolver."""
    resolver = my_profile_resolver
    
    test_cases = [
        Flags(is_registered=False, has_vehicle=False),
        Flags(is_registered=True, has_vehicle=False),
        Flags(is_registered=True, has_vehicle=True),
    ]
    
    for flags in test_cases:
        try:
            profile = resolver(flags)
            print(f"Flags: {flags} → Profile: {profile}")
        except Exception as e:
            print(f"❌ Resolver error: {e}")
```

### Test Command Building

```python
async def test_command_building():
    """Test command building."""
    from aiogram_cmds import build_bot_commands
    
    commands = build_bot_commands(
        ["start", "help"],
        lang="en",
        translator=my_translator
    )
    
    for cmd in commands:
        print(f"Command: {cmd.command}, Description: {cmd.description}")
```

### Test Translator

```python
def test_translator():
    """Test your translator."""
    translator = build_translator_from_i18n(i18n)
    
    test_keys = [
        "cmd.start.desc",
        "cmd.help.desc",
        "cmd.profile.desc",
    ]
    
    for key in test_keys:
        for lang in ["en", "ru", "es"]:
            result = translator(key, locale=lang)
            print(f"{key} ({lang}): {result}")
```

## 🚨 Error Messages

### Common Error Messages and Solutions

#### `ValidationError: field required`
```
❌ Error: ValidationError: field required
✅ Solution: Check that all required fields are provided in your configuration
```

#### `ValueError: Unknown scope: invalid_scope`
```
❌ Error: ValueError: Unknown scope: invalid_scope
✅ Solution: Use valid scope types: default, all_private_chats, all_group_chats, etc.
```

#### `KeyError: 'profile_name'`
```
❌ Error: KeyError: 'profile_name'
✅ Solution: Make sure the profile is defined in your configuration
```

#### `TypeError: 'NoneType' object is not callable`
```
❌ Error: TypeError: 'NoneType' object is not callable
✅ Solution: Check that your translator function is properly defined
```

## 📞 Getting Help

### Before Asking for Help

1. **Check the logs** - Enable debug logging and check for error messages
2. **Test your configuration** - Use the debugging tools above
3. **Check the documentation** - Review the relevant guides
4. **Search existing issues** - Check GitHub issues for similar problems

### When Asking for Help

Provide the following information:

1. **Error message** - Full error traceback
2. **Code snippet** - Minimal code that reproduces the issue
3. **Configuration** - Your configuration (without sensitive data)
4. **Environment** - Python version, aiogram version, aiogram-cmds version
5. **Steps to reproduce** - Clear steps to reproduce the issue

### Where to Get Help

- [GitHub Discussions](https://github.com/ArmanAvanesyan/aiogram-cmds/discussions) - Community help
- [GitHub Issues](https://github.com/ArmanAvanesyan/aiogram-cmds/issues) - Bug reports
- [Documentation](https://aiogram-cmds.dev) - Complete guides

---

**Still having issues?** Check out our [FAQ](faq.md) or [create an issue](https://github.com/ArmanAvanesyan/aiogram-cmds/issues) with the information above!
