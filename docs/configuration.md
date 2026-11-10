# Configuration Guide

This guide covers all configuration options available in aiogram-cmds, from simple settings to advanced configurations.

## 📋 Overview

aiogram-cmds supports three configuration approaches:

1. **Auto-Setup**: Zero configuration, works out of the box
2. **Simple Mode**: Settings-based configuration with policies
3. **Advanced Mode**: Full control with profiles, scopes, and custom resolvers

## 🚀 Auto-Setup Configuration

The simplest way to get started - no configuration required:

```python
from aiogram_cmds.auto_setup import setup_commands_auto

# Automatically set up with sensible defaults
manager = await setup_commands_auto(bot)
```

**Default Configuration:**
- Languages: `["en"]`
- Commands: `["start", "help", "cancel"]`
- Profiles: `guest` (includes start, help), `user` (includes start, help, cancel)
- Scopes: `all_private_chats` with `guest` profile
- Menu button: `commands`

## ⚙️ Simple Mode Configuration

### CmdsSettings

Use `CmdsSettings` for basic configuration:

```python
from aiogram_cmds import CmdsSettings, CommandScopeManager

settings = CmdsSettings(
    languages=["en", "ru", "es"],
    fallback_language="en",
    i18n_key_prefix="cmd",
    profile="default",
    menu_button="commands"
)

manager = CommandScopeManager(bot, settings=settings)
```

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `languages` | `List[str]` | `["en"]` | Supported language codes |
| `fallback_language` | `str` | `"en"` | Fallback language for missing translations |
| `i18n_key_prefix` | `str` | `"cmd"` | Prefix for i18n translation keys |
| `profile` | `str` | `"default"` | Default profile name |
| `menu_button` | `str` | `"commands"` | Menu button mode ("commands" or "default") |

### Loading from pyproject.toml

Create `pyproject.toml`:

```toml
[tool.aiogram_cmds]
languages = ["en", "ru", "es"]
fallback_language = "en"
i18n_key_prefix = "cmd"
profile = "default"
menu_button = "commands"
```

Load in your code:

```python
from aiogram_cmds import load_settings

settings = load_settings()  # Loads from pyproject.toml
manager = CommandScopeManager(bot, settings=settings)
```

## 🎛️ Advanced Mode Configuration

### CmdsConfig

Full control with `CmdsConfig`:

```python
from aiogram_cmds import CmdsConfig, CommandDef, ProfileDef, ScopeDef, MenuButtonDef

config = CmdsConfig(
    languages=["en", "ru", "es"],
    fallback_language="en",
    i18n_key_prefix="cmd",
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "help": CommandDef(i18n_key="help.desc"),
        "profile": CommandDef(i18n_key="profile.desc"),
    },
    profiles={
        "guest": ProfileDef(include=["start", "help"]),
        "user": ProfileDef(include=["start", "help", "profile"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="guest"),
    ],
    menu_button=MenuButtonDef(mode="commands"),
)

manager = CommandScopeManager(bot, config=config)
```

### Command Definitions

#### CommandDef

Define individual commands:

```python
# Using i18n key
start_cmd = CommandDef(i18n_key="start.desc")

# Using inline descriptions
help_cmd = CommandDef(descriptions={
    "en": "Show help information",
    "ru": "Показать справку",
    "es": "Mostrar ayuda"
})

# Using both (i18n takes precedence)
profile_cmd = CommandDef(
    i18n_key="profile.desc",
    descriptions={"en": "View your profile"},
    tags=["user", "profile"]
)
```

**Fields:**
- `i18n_key` (`str`, optional): i18n key for command description
- `descriptions` (`Dict[str, str]`): Inline descriptions by language
- `tags` (`List[str]`): Command tags for organization

#### Description Resolution Order

1. i18n_key with translator (if available)
2. Inline descriptions for specific language
3. Fallback to Title Case of command name

### Profile Definitions

#### ProfileDef

Define user profiles:

```python
# Basic profile
guest_profile = ProfileDef(include=["start", "help"])

# Profile with exclusions
admin_profile = ProfileDef(
    include=["start", "help", "profile", "admin", "settings"],
    exclude=["settings"]  # Remove settings from admin profile
)

# Complex profile
vip_profile = ProfileDef(
    include=["start", "help", "profile", "vip_offers", "premium_support"],
    exclude=["basic_features"]
)
```

**Fields:**
- `include` (`List[str]`): Commands to include in this profile
- `exclude` (`List[str]`): Commands to exclude from this profile

**Logic:**
1. Start with all commands from `include` list
2. Remove any commands that exist in `exclude` list
3. Only include commands that are defined in the commands registry

### Scope Definitions

#### ScopeDef

Define command scopes:

```python
# Global scope
default_scope = ScopeDef(scope="all_private_chats", profile="guest")

# Chat-specific scope
admin_chat_scope = ScopeDef(
    scope="chat",
    chat_id=12345,
    profile="admin",
    languages=["en", "ru"]
)

# User-specific scope
vip_user_scope = ScopeDef(
    scope="chat_member",
    chat_id=12345,
    user_id=67890,
    profile="vip"
)
```

**Fields:**
- `scope` (`ScopeType`): Telegram command scope type
- `profile` (`str`): Profile name to apply
- `chat_id` (`int`, optional): Chat ID for chat-specific scopes
- `user_id` (`int`, optional): User ID for user-specific scopes
- `languages` (`List[str]`): Languages for this scope (empty = use global)

#### Scope Types

```python
ScopeType = Literal[
    "default",                    # Global default
    "all_private_chats",         # All private chats
    "all_group_chats",           # All group chats
    "all_chat_admins",           # All chat administrators
    "chat",                      # Specific chat
    "chat_admins",               # Administrators in specific chat
    "chat_member",               # Specific user in specific chat
]
```

#### Scope Hierarchy

Scopes are applied in order of specificity (most specific first):

1. **chat_member** - Specific user in specific chat
2. **chat_admins** - All admins in specific chat
3. **chat** - All users in specific chat
4. **all_chat_admins** - All chat administrators globally
5. **all_group_chats** - All group chats
6. **all_private_chats** - All private chats
7. **default** - Global fallback

### Menu Button Configuration

#### MenuButtonDef

Configure the menu button:

```python
# Enable commands menu button
menu_button = MenuButtonDef(mode="commands")

# Use default menu button
menu_button = MenuButtonDef(mode="default")
```

**Fields:**
- `mode` (`str`): Menu button mode ("commands" or "default")

## 🔧 Profile Resolvers

### Simple Profile Resolver

```python
from aiogram_cmds import ProfileResolver, Flags

def simple_profile_resolver(flags: Flags) -> str:
    if flags.is_registered:
        return "user"
    return "guest"

manager = CommandScopeManager(bot, profile_resolver=simple_profile_resolver)
```

### Advanced Profile Resolver

```python
def advanced_profile_resolver(flags: Flags) -> str:
    user_id = getattr(flags, 'user_id', None)
    if not user_id:
        return "guest"
    
    # Get user data from database
    user_data = get_user_from_database(user_id)
    
    if user_data.get("banned", False):
        return "banned"
    elif user_data.get("admin", False):
        return "admin"
    elif user_data.get("premium", False):
        return "premium"
    elif user_data.get("registered", False):
        return "user"
    
    return "guest"

manager = CommandScopeManager(bot, profile_resolver=advanced_profile_resolver)
```

### Context-Aware Resolver

```python
def context_aware_resolver(flags: Flags) -> str:
    user_id = getattr(flags, 'user_id', None)
    chat_id = getattr(flags, 'chat_id', None)
    
    if not user_id:
        return "guest"
    
    # Check user status
    user_data = get_user_from_database(user_id)
    
    # Check chat-specific permissions
    if chat_id:
        chat_permissions = get_chat_permissions(user_id, chat_id)
        if chat_permissions.get("admin", False):
            return "chat_admin"
        elif chat_permissions.get("moderator", False):
            return "chat_moderator"
    
    # Standard profile logic
    if user_data.get("banned", False):
        return "banned"
    elif user_data.get("admin", False):
        return "admin"
    elif user_data.get("premium", False):
        return "premium"
    elif user_data.get("registered", False):
        return "user"
    
    return "guest"
```

## 🌍 i18n Configuration

### Basic i18n Setup

```python
from aiogram_cmds import build_translator_from_i18n

# With aiogram i18n
translator = build_translator_from_i18n(i18n_instance)
manager = CommandScopeManager(bot, translator=translator)
```

### Custom Translator

```python
def custom_translator(key: str, *, locale: str) -> str:
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
    return translations.get(locale, {}).get(key)

manager = CommandScopeManager(bot, translator=custom_translator)
```

### Translation Key Patterns

#### Default Pattern
```
{prefix}.{command}.desc
```

Example: `cmd.start.desc` → "Start the bot"

#### Custom Patterns
```python
commands = {
    "start": CommandDef(i18n_key="commands.start.description"),
    "help": CommandDef(i18n_key="menu.help.tooltip"),
    "admin": CommandDef(i18n_key="admin.panel.commands.open"),
}
```

## 📝 Configuration Examples

### E-commerce Bot

```python
config = CmdsConfig(
    languages=["en", "ru"],
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "catalog": CommandDef(i18n_key="catalog.desc"),
        "cart": CommandDef(i18n_key="cart.desc"),
        "orders": CommandDef(i18n_key="orders.desc"),
        "vip_offers": CommandDef(i18n_key="vip_offers.desc"),
        "help": CommandDef(i18n_key="help.desc"),
    },
    profiles={
        "visitor": ProfileDef(include=["start", "catalog", "help"]),
        "customer": ProfileDef(include=["start", "catalog", "cart", "orders", "help"]),
        "vip": ProfileDef(include=["start", "catalog", "cart", "orders", "vip_offers", "help"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="visitor"),
    ],
)
```

### Admin Bot

```python
config = CmdsConfig(
    languages=["en"],
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "help": CommandDef(i18n_key="help.desc"),
        "profile": CommandDef(i18n_key="profile.desc"),
        "admin": CommandDef(i18n_key="admin.desc"),
        "ban": CommandDef(i18n_key="ban.desc"),
        "unban": CommandDef(i18n_key="unban.desc"),
    },
    profiles={
        "user": ProfileDef(include=["start", "help", "profile"]),
        "admin": ProfileDef(include=["start", "help", "profile", "admin", "ban", "unban"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="user"),
        ScopeDef(scope="chat", chat_id=admin_chat_id, profile="admin"),
    ],
)
```

### Multi-Language Bot

```python
config = CmdsConfig(
    languages=["en", "ru", "es", "fr"],
    fallback_language="en",
    commands={
        "start": CommandDef(i18n_key="commands.start"),
        "help": CommandDef(i18n_key="commands.help"),
        "language": CommandDef(i18n_key="commands.language"),
    },
    profiles={
        "default": ProfileDef(include=["start", "help", "language"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="default"),
    ],
)
```

## 🔍 Configuration Validation

### Pydantic Validation

All configuration models use Pydantic for validation:

```python
# This will raise ValidationError
invalid_config = CmdsConfig(
    languages=[],  # Empty languages list
    fallback_language="invalid",  # Not in languages list
)
```

### Common Validation Errors

#### Empty Languages List
```python
# ❌ Invalid
config = CmdsConfig(languages=[])

# ✅ Valid
config = CmdsConfig(languages=["en"])
```

#### Invalid Fallback Language
```python
# ❌ Invalid
config = CmdsConfig(
    languages=["en", "ru"],
    fallback_language="es"  # Not in languages list
)

# ✅ Valid
config = CmdsConfig(
    languages=["en", "ru"],
    fallback_language="en"  # In languages list
)
```

#### Undefined Profile Reference
```python
# ❌ Invalid
config = CmdsConfig(
    profiles={"user": ProfileDef(include=["start"])},
    scopes=[ScopeDef(scope="all_private_chats", profile="admin")]  # Profile not defined
)

# ✅ Valid
config = CmdsConfig(
    profiles={"user": ProfileDef(include=["start"])},
    scopes=[ScopeDef(scope="all_private_chats", profile="user")]
)
```

## 🚨 Best Practices

### 1. Use Consistent Naming
```python
# ✅ Good - Consistent naming
profiles = {
    "guest": ProfileDef(include=["start", "help"]),
    "user": ProfileDef(include=["start", "help", "profile"]),
    "admin": ProfileDef(include=["start", "help", "profile", "admin"]),
}

# ❌ Avoid - Inconsistent naming
profiles = {
    "basic": ProfileDef(include=["start"]),
    "advanced": ProfileDef(include=["start", "help", "profile", "admin"]),
}
```

### 2. Organize Commands Logically
```python
# ✅ Good - Logical organization
commands = {
    # Basic commands
    "start": CommandDef(i18n_key="start.desc"),
    "help": CommandDef(i18n_key="help.desc"),
    
    # User commands
    "profile": CommandDef(i18n_key="profile.desc"),
    "settings": CommandDef(i18n_key="settings.desc"),
    
    # Admin commands
    "admin": CommandDef(i18n_key="admin.desc"),
    "ban": CommandDef(i18n_key="ban.desc"),
}
```

### 3. Use Appropriate Scopes
```python
# ✅ Good - Specific scopes for specific needs
scopes = [
    ScopeDef(scope="all_private_chats", profile="user"),
    ScopeDef(scope="chat", chat_id=admin_chat_id, profile="admin"),
]

# ❌ Avoid - Overly broad scopes
scopes = [
    ScopeDef(scope="default", profile="admin"),  # Too broad
]
```

### 4. Validate Configuration
```python
# ✅ Good - Validate configuration
try:
    config = CmdsConfig.model_validate(config_data)
except ValidationError as e:
    logger.error(f"Invalid configuration: {e}")
    return
```

### 5. Use i18n Keys
```python
# ✅ Good - Uses i18n keys
commands = {
    "start": CommandDef(i18n_key="commands.start.description"),
    "help": CommandDef(i18n_key="commands.help.description"),
}

# ❌ Avoid - Hardcoded descriptions
commands = {
    "start": CommandDef(descriptions={"en": "Start the bot"}),
    "help": CommandDef(descriptions={"en": "Show help"}),
}
```

## 🔧 Configuration Loading

### From pyproject.toml
```toml
[tool.aiogram_cmds]
languages = ["en", "ru", "es"]
fallback_language = "en"
i18n_key_prefix = "cmd"
profile = "default"
menu_button = "commands"
```

### From JSON
```python
import json
from aiogram_cmds import CmdsConfig

with open("config.json") as f:
    data = json.load(f)
    config = CmdsConfig.model_validate(data)
```

### From YAML
```python
import yaml
from aiogram_cmds import CmdsConfig

with open("config.yaml") as f:
    data = yaml.safe_load(f)
    config = CmdsConfig.model_validate(data)
```

### From Environment Variables
```python
import os
from aiogram_cmds import CmdsConfig

config = CmdsConfig(
    languages=os.getenv("BOT_LANGUAGES", "en").split(","),
    fallback_language=os.getenv("BOT_FALLBACK_LANGUAGE", "en"),
    i18n_key_prefix=os.getenv("BOT_I18N_PREFIX", "cmd"),
)
```

## 🎯 Configuration Tips

- Start with auto-setup, then customize as needed
- Use configuration files for persistent settings
- Validate all configurations before use
- Use consistent naming conventions
- Organize commands and profiles logically
- Test all configuration combinations
- Use i18n keys for multi-language support
- Implement proper error handling for configuration loading

---

For more information about using configurations, see:
- [Quickstart Guide](quickstart.md) - Getting started with configurations
- [API Reference](api/configuration.md) - Detailed API documentation
- [Tutorials](tutorials/basic-setup.md) - Step-by-step configuration guides
