## Translator Protocol

`aiogram_cmds.translator.Translator` is a callable used to resolve localized strings.

Signature:

```python
def __call__(
    key: str,
    *,
    locale: str | None = None,
    plural: str | None = None,
    count: int | None = None,
) -> str | None: ...
```

- Returns `None` if translation is missing (callers should fallback)
- `locale` can be omitted to use ambient middleware context
- When `plural` and `count` are provided, plural form is used (maps to `ngettext`)

### Adapter

```python
from aiogram_cmds import build_translator_from_i18n
translator = build_translator_from_i18n(i18n)
```

The adapter uses `I18n.with_locale(locale)` when `locale` is provided, otherwise `gettext`/`ngettext` use the current context.

# Translator API Reference

This document provides detailed API reference for the translation system and i18n integration in aiogram-cmds.

## Translator Protocol

The translator system is built around a simple protocol that allows for flexible i18n integration.

```python
class Translator(Protocol):
    def __call__(self, key: str, *, locale: str) -> Optional[str]: ...
```

**Parameters:**
- **key** (`str`): Translation key to look up
- **locale** (`str`): Language code (e.g., "en", "ru", "es")

**Returns:**
- `Optional[str]`: Translated text or None if not found

## Built-in Translators

### `build_translator_from_i18n()`

Create a translator adapter from an aiogram i18n instance.

```python
def build_translator_from_i18n(i18n_obj) -> Translator:
    """Build translator adapter from an aiogram i18n instance."""
```

**Parameters:**
- **i18n_obj**: aiogram i18n instance with `gettext(key, locale=?)` method

**Returns:**
- `Translator`: Translator function that can be used with aiogram-cmds

**Behavior:**
- Calls `i18n_obj.gettext(key, locale=locale)`
- Returns None if translation is missing or equals the key
- Handles exceptions gracefully

**Example:**
```python
from aiogram_cmds import build_translator_from_i18n

# Assuming you have an aiogram i18n instance
translator = build_translator_from_i18n(i18n)

# Use with CommandScopeManager
manager = CommandScopeManager(bot, translator=translator)
```

### `noop_translator()`

No-operation translator that always returns None.

```python
def noop_translator(key: str, *, locale: str) -> Optional[str]:
    """No-op translator that always returns None."""
    return None
```

**Use Cases:**
- Testing and development
- When i18n is not needed
- Fallback when no translator is available

**Example:**
```python
from aiogram_cmds import noop_translator

# Use no-op translator
manager = CommandScopeManager(bot, translator=noop_translator)
```

## Custom Translators

You can create custom translators by implementing the Translator protocol.

### Simple Dictionary Translator

```python
from typing import Dict, Optional
from aiogram_cmds import Translator

class DictTranslator:
    def __init__(self, translations: Dict[str, Dict[str, str]]):
        self.translations = translations
    
    def __call__(self, key: str, *, locale: str) -> Optional[str]:
        return self.translations.get(locale, {}).get(key)

# Usage
translations = {
    "en": {
        "cmd.start.desc": "Start the bot",
        "cmd.help.desc": "Show help information",
    },
    "ru": {
        "cmd.start.desc": "Запустить бота",
        "cmd.help.desc": "Показать справку",
    }
}

translator = DictTranslator(translations)
manager = CommandScopeManager(bot, translator=translator)
```

### File-based Translator

```python
import json
from pathlib import Path
from typing import Optional

class FileTranslator:
    def __init__(self, locales_dir: Path):
        self.locales_dir = locales_dir
        self._cache = {}
    
    def __call__(self, key: str, *, locale: str) -> Optional[str]:
        if locale not in self._cache:
            locale_file = self.locales_dir / f"{locale}.json"
            if locale_file.exists():
                with open(locale_file) as f:
                    self._cache[locale] = json.load(f)
            else:
                self._cache[locale] = {}
        
        return self._cache[locale].get(key)

# Usage
translator = FileTranslator(Path("locales"))
manager = CommandScopeManager(bot, translator=translator)
```

### Database Translator

```python
import asyncio
from typing import Optional

class DatabaseTranslator:
    def __init__(self, db_connection):
        self.db = db_connection
    
    def __call__(self, key: str, *, locale: str) -> Optional[str]:
        # This is a synchronous interface, so we need to handle async carefully
        # In practice, you might want to preload translations or use a sync DB client
        try:
            # Assuming you have a sync database client
            result = self.db.execute(
                "SELECT translation FROM translations WHERE key = ? AND locale = ?",
                (key, locale)
            ).fetchone()
            return result[0] if result else None
        except Exception:
            return None

# Usage
translator = DatabaseTranslator(db_connection)
manager = CommandScopeManager(bot, translator=translator)
```

## Translation Key Patterns

### Default Pattern

The default translation key pattern is:
```
{prefix}.{command}.desc
```

Where:
- `prefix` is the `i18n_key_prefix` from configuration (default: "cmd")
- `command` is the command name
- `desc` is the description suffix

**Example:**
```python
# Configuration
config = CmdsConfig(
    i18n_key_prefix="cmd",
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "help": CommandDef(i18n_key="help.desc"),
    }
)

# Translation keys
# cmd.start.desc -> "Start the bot"
# cmd.help.desc -> "Show help information"
```

### Custom Patterns

You can use custom patterns by setting the `i18n_key` in CommandDef:

```python
commands = {
    "start": CommandDef(i18n_key="commands.start.description"),
    "help": CommandDef(i18n_key="commands.help.description"),
    "profile": CommandDef(i18n_key="menu.profile.tooltip"),
}
```

### Nested Patterns

For complex bots, you might want nested translation keys:

```python
commands = {
    "start": CommandDef(i18n_key="bot.commands.start.description"),
    "help": CommandDef(i18n_key="bot.commands.help.description"),
    "admin_panel": CommandDef(i18n_key="admin.panel.commands.open.description"),
}
```

## Fallback Strategy

The translation system implements a multi-level fallback strategy:

### 1. Primary Translation
Try to get translation for the requested key and locale.

```python
# Try: cmd.start.desc with locale "ru"
translation = translator("cmd.start.desc", locale="ru")
```

### 2. Fallback Language
If primary translation fails, try with the fallback language.

```python
# Try: cmd.start.desc with locale "en" (fallback)
translation = translator("cmd.start.desc", locale="en")
```

### 3. Title Case Fallback
If both translations fail, use Title Case of the command name.

```python
# Fallback: "Start" (from command name "start")
translation = "Start"
```

### 4. Final Fallback
If all else fails, use "Command" as the description.

```python
# Final fallback
translation = "Command"
```

## Integration with aiogram i18n

### Basic Integration

```python
from aiogram import Bot, Dispatcher
from aiogram.utils.i18n import I18n, FSMI18nMiddleware
from aiogram_cmds import build_translator_from_i18n, CommandScopeManager

# Set up aiogram i18n
i18n = I18n(path="locales", default_locale="en", domain="messages")
dp.message.middleware(FSMI18nMiddleware(i18n))

# Create translator
translator = build_translator_from_i18n(i18n)

# Use with aiogram-cmds
manager = CommandScopeManager(bot, translator=translator)
```

### Advanced Integration

```python
from aiogram.utils.i18n import I18n
from aiogram_cmds import build_translator_from_i18n

class CustomTranslator:
    def __init__(self, i18n: I18n):
        self.i18n = i18n
    
    def __call__(self, key: str, *, locale: str) -> Optional[str]:
        try:
            # Use aiogram's i18n with custom context
            translation = self.i18n.gettext(key, locale=locale)
            
            # Additional processing
            if translation and translation != key:
                return translation.upper()  # Example: make all caps
            
            return None
        except Exception:
            return None

# Usage
translator = CustomTranslator(i18n)
manager = CommandScopeManager(bot, translator=translator)
```

## Translation Files Structure

### JSON Structure

```json
// locales/en.json
{
  "cmd.start.desc": "Start the bot",
  "cmd.help.desc": "Show help information",
  "cmd.profile.desc": "View your profile",
  "cmd.settings.desc": "Bot settings"
}

// locales/ru.json
{
  "cmd.start.desc": "Запустить бота",
  "cmd.help.desc": "Показать справку",
  "cmd.profile.desc": "Посмотреть профиль",
  "cmd.settings.desc": "Настройки бота"
}
```

### YAML Structure

```yaml
# locales/en.yaml
cmd:
  start:
    desc: "Start the bot"
  help:
    desc: "Show help information"
  profile:
    desc: "View your profile"

# locales/ru.yaml
cmd:
  start:
    desc: "Запустить бота"
  help:
    desc: "Показать справку"
  profile:
    desc: "Посмотреть профиль"
```

### PO/POT Structure

```po
# locales/en/LC_MESSAGES/messages.po
msgid "cmd.start.desc"
msgstr "Start the bot"

msgid "cmd.help.desc"
msgstr "Show help information"

# locales/ru/LC_MESSAGES/messages.po
msgid "cmd.start.desc"
msgstr "Запустить бота"

msgid "cmd.help.desc"
msgstr "Показать справку"
```

## Best Practices

### 1. Use Consistent Key Patterns

```python
# ✅ Good - Consistent pattern
commands = {
    "start": CommandDef(i18n_key="start.desc"),
    "help": CommandDef(i18n_key="help.desc"),
    "profile": CommandDef(i18n_key="profile.desc"),
}

# ❌ Avoid - Inconsistent patterns
commands = {
    "start": CommandDef(i18n_key="start.desc"),
    "help": CommandDef(i18n_key="commands.help"),
    "profile": CommandDef(i18n_key="user.profile.description"),
}
```

### 2. Provide Fallback Translations

```python
# ✅ Good - Provide fallback descriptions
commands = {
    "start": CommandDef(
        i18n_key="start.desc",
        descriptions={"en": "Start the bot"}
    ),
}

# ❌ Avoid - No fallback
commands = {
    "start": CommandDef(i18n_key="start.desc"),  # No fallback if translation missing
}
```

### 3. Test Translation Coverage

```python
def test_translation_coverage():
    """Test that all commands have translations."""
    config = load_config()
    translator = build_translator_from_i18n(i18n)
    
    for lang in config.languages:
        for cmd_name, cmd_def in config.commands.items():
            if cmd_def.i18n_key:
                key = f"{config.i18n_key_prefix}.{cmd_def.i18n_key}"
                translation = translator(key, locale=lang)
                assert translation is not None, f"Missing translation for {key} in {lang}"
```

### 4. Handle Translation Errors Gracefully

```python
class SafeTranslator:
    def __init__(self, base_translator: Translator):
        self.base_translator = base_translator
    
    def __call__(self, key: str, *, locale: str) -> Optional[str]:
        try:
            return self.base_translator(key, locale=locale)
        except Exception as e:
            logger.warning(f"Translation error for {key} in {locale}: {e}")
            return None

# Usage
safe_translator = SafeTranslator(translator)
manager = CommandScopeManager(bot, translator=safe_translator)
```

## Debugging Translations

### Enable Debug Logging

```python
import logging
logging.getLogger("aiogram_cmds").setLevel(logging.DEBUG)
```

### Test Translations

```python
def test_translations():
    translator = build_translator_from_i18n(i18n)
    
    # Test specific keys
    keys = ["cmd.start.desc", "cmd.help.desc", "cmd.profile.desc"]
    locales = ["en", "ru", "es"]
    
    for key in keys:
        for locale in locales:
            translation = translator(key, locale=locale)
            print(f"{key} ({locale}): {translation}")
```

### Missing Translation Detection

```python
def find_missing_translations():
    """Find commands without translations."""
    config = load_config()
    translator = build_translator_from_i18n(i18n)
    
    missing = []
    for lang in config.languages:
        for cmd_name, cmd_def in config.commands.items():
            if cmd_def.i18n_key:
                key = f"{config.i18n_key_prefix}.{cmd_def.i18n_key}"
                translation = translator(key, locale=lang)
                if translation is None:
                    missing.append((key, lang))
    
    return missing
```

---

For more information about using translators, see:
- [Core API](core.md) - How to use translators with CommandScopeManager
- [Configuration API](configuration.md) - Configuring i18n settings
- [Quickstart Guide](../quickstart.md) - Getting started with i18n
