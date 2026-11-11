# Core API Reference

This document provides detailed API reference for the core components of aiogram-cmds.

## CommandScopeManager

The central orchestrator for command management operations.

```python
class CommandScopeManager:
    def __init__(
        self,
        bot: Bot,
        *,
        settings: Optional[CmdsSettings] = None,
        config: Optional[CmdsConfig] = None,
        translator: Optional[Translator] = None,
        policy: Optional[CommandPolicy] = None,
        profile_resolver: Optional[ProfileResolver] = None,
    ) -> None
```

### Parameters

- **bot** (`Bot`): The aiogram Bot instance
- **settings** (`CmdsSettings`, optional): Simple mode configuration
- **config** (`CmdsConfig`, optional): Advanced mode configuration  
- **translator** (`Translator`, optional): i18n translation function
- **policy** (`CommandPolicy`, optional): Command policy for simple mode
- **profile_resolver** (`ProfileResolver`, optional): Profile resolver for advanced mode

### Methods

#### `async setup_all() -> None`

Set up all command scopes and menu button.

**Behavior:**
- If `config` is provided: applies full configuration (advanced mode)
- Otherwise: applies settings-based configuration (simple mode)
- Sets up menu button according to configuration
- Applies scopes in order of specificity

**Example:**
```python
await manager.setup_all()
```

#### `async update_user_commands(user_id: int, **flags) -> None`

Update commands for a specific user based on their flags.

**Parameters:**
- **user_id** (`int`): Telegram user ID
- **is_registered** (`bool`): Whether user is registered
- **has_vehicle** (`bool`): Whether user has a vehicle
- **is_during_registration** (`bool`, optional): Whether user is in registration process
- **user_language** (`str`, optional): User's preferred language (default: "en")
- **chat_id** (`int`, optional): Specific chat ID for chat-specific commands

**Behavior:**
- Creates Flags object from parameters
- Resolves profile using policy or profile_resolver
- Builds command list from resolved profile
- Applies commands to user's private chat scope

**Example:**
```python
await manager.update_user_commands(
    user_id=12345,
    is_registered=True,
    has_vehicle=False,
    user_language="en"
)
```

#### `async clear_user_commands(user_id: int) -> None`

Clear user-specific command overrides.

**Parameters:**
- **user_id** (`int`): Telegram user ID

**Behavior:**
- Deletes user-specific command scope
- User falls back to broader scope commands
- Logs the operation

**Example:**
```python
await manager.clear_user_commands(12345)
```

## Builder Functions

### `build_bot_commands()`

Build BotCommand objects from command names with i18n descriptions.

```python
def build_bot_commands(
    command_names: List[str],
    *,
    lang: str,
    translator: Optional[Translator] = None,
    key_prefix: str = "cmd",
) -> List[BotCommand]
```

**Parameters:**
- **command_names** (`List[str]`): List of command names to build
- **lang** (`str`): Language code for descriptions
- **translator** (`Translator`, optional): Translation function
- **key_prefix** (`str`): Prefix for i18n keys (default: "cmd")

**Returns:**
- `List[BotCommand]`: List of BotCommand objects ready for Telegram API

**Behavior:**
- Validates and sanitizes command names
- Resolves descriptions via translator
- Falls back to Title Case if translation fails
- Enforces Telegram API constraints (length, characters)

**Example:**
```python
commands = build_bot_commands(
    ["start", "help", "profile"],
    lang="en",
    translator=my_translator,
    key_prefix="cmd"
)
```

## Policy System

### CommandPolicy Protocol

Protocol for command policy functions in simple mode.

```python
class CommandPolicy(Protocol):
    def __call__(self, flags: Flags) -> List[str]: ...
```

**Parameters:**
- **flags** (`Flags`): User flags object

**Returns:**
- `List[str]`: List of command names for the user

### ProfileResolver Protocol

Protocol for profile resolver functions in advanced mode.

```python
class ProfileResolver(Protocol):
    def __call__(self, flags: Flags) -> str: ...
```

**Parameters:**
- **flags** (`Flags`): User flags object

**Returns:**
- `str`: Profile name for the user

### Flags Dataclass

User flags that determine command availability.

```python
@dataclass(frozen=True)
class Flags:
    is_registered: bool
    has_vehicle: bool
    is_during_registration: bool = False
```

**Fields:**
- **is_registered** (`bool`): Whether user is registered
- **has_vehicle** (`bool`): Whether user has a vehicle
- **is_during_registration** (`bool`): Whether user is in registration process

### Default Policy

Built-in command policy for simple mode.

```python
def default_policy(flags: Flags) -> List[str]:
    """Minimal, project-agnostic command policy."""
    if flags.is_during_registration or not flags.is_registered:
        return ["start", "cancel"]
    return ["start", "help", "cancel", "profile", "settings"]
```

## Settings System

### CmdsSettings

Configuration class for simple mode.

```python
class CmdsSettings(BaseModel):
    languages: List[str] = ["en"]
    fallback_language: str = "en"
    i18n_key_prefix: str = "cmd"
    profile: str = "default"
    menu_button: str = "commands"  # "commands" | "default"
```

**Fields:**
- **languages** (`List[str]`): Supported language codes
- **fallback_language** (`str`): Fallback language for missing translations
- **i18n_key_prefix** (`str`): Prefix for i18n translation keys
- **profile** (`str`): Default profile name
- **menu_button** (`str`): Menu button mode ("commands" or "default")

### `load_settings()`

Load settings from pyproject.toml configuration.

```python
def load_settings(pyproject_path: Optional[Path] = None) -> CmdsSettings
```

**Parameters:**
- **pyproject_path** (`Path`, optional): Path to pyproject.toml file

**Returns:**
- `CmdsSettings`: Loaded settings or defaults if not found

**Behavior:**
- Reads `[tool.aiogram_cmds]` section from pyproject.toml
- Returns default settings if file not found or invalid
- Logs warnings for configuration errors

**Example:**
```python
settings = load_settings()  # Uses pyproject.toml in current directory
settings = load_settings(Path("custom.toml"))  # Uses custom file
```

## Auto-Setup

### `setup_commands_auto()`

Automatically set up command management with minimal configuration.

```python
async def setup_commands_auto(
    bot: Bot,
    *,
    languages: Optional[List[str]] = None,
    i18n_instance = None,
    config: Optional[CmdsConfig] = None,
    profile_resolver: Optional[ProfileResolver] = None,
) -> CommandScopeManager
```

**Parameters:**
- **bot** (`Bot`): Telegram Bot instance
- **languages** (`List[str]`, optional): Supported languages (default: ["en"])
- **i18n_instance**: aiogram i18n instance (auto-detected if not provided)
- **config** (`CmdsConfig`, optional): Custom configuration
- **profile_resolver** (`ProfileResolver`, optional): Custom profile resolver

**Returns:**
- `CommandScopeManager`: Configured and ready-to-use manager

**Behavior:**
- Creates default configuration if not provided
- Attempts to auto-detect i18n instance
- Sets up all command scopes and menu button
- Returns ready-to-use manager

**Example:**
```python
manager = await setup_commands_auto(bot)
# Commands are automatically configured and ready!
```

## Error Handling

### Common Exceptions

#### `ValueError`
Raised for invalid configuration or parameters:
- Invalid command names
- Invalid scope types
- Missing required parameters

#### `KeyError`
Raised for missing configuration:
- Undefined profiles
- Missing command definitions
- Invalid profile references

#### `TypeError`
Raised for type mismatches:
- Invalid translator function
- Wrong parameter types
- Protocol violations

### Error Recovery

The library implements graceful error recovery:

1. **i18n Failures**: Falls back to Title Case descriptions
2. **Missing Profiles**: Returns empty command list
3. **Invalid Commands**: Skips invalid commands, continues with valid ones
4. **API Failures**: Logs errors, continues with other operations

### Logging

All operations are logged with appropriate levels:

- **DEBUG**: Detailed operation information
- **INFO**: Successful operations and status changes
- **WARNING**: Recoverable errors and fallbacks
- **ERROR**: Unrecoverable errors and exceptions

**Example:**
```python
import logging
logging.getLogger("aiogram_cmds").setLevel(logging.DEBUG)
```

## Type Hints

All functions and classes include comprehensive type hints:

```python
from typing import Optional, List, Dict, Protocol
from aiogram import Bot
from aiogram.types import BotCommand

# Example type hints
def build_commands(
    names: List[str],
    lang: str,
    translator: Optional[Translator] = None
) -> List[BotCommand]:
    ...
```

## Thread Safety

aiogram-cmds is designed for async/await usage:

- All public methods are `async`
- No thread-safe operations required
- Compatible with aiogram's async architecture
- Safe for concurrent usage in async contexts

---

For more detailed information about specific components, see:
- [Configuration API](configuration.md) - Configuration models and options
- [Translator API](translator.md) - Translation system and i18n integration
