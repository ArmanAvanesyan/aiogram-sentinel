# Configuration API Reference

This document provides detailed API reference for configuration models and options in aiogram-cmds.

## Configuration Models

### CmdsConfig

Full customizable configuration for advanced mode.

```python
class CmdsConfig(BaseModel):
    languages: List[str] = ["en"]
    fallback_language: str = "en"
    i18n_key_prefix: str = "cmd"
    commands: Dict[str, CommandDef] = Field(default_factory=dict)
    profiles: Dict[str, ProfileDef] = Field(default_factory=dict)
    scopes: List[ScopeDef] = Field(default_factory=list)
    menu_button: MenuButtonDef = Field(default_factory=MenuButtonDef)
```

**Fields:**
- **languages** (`List[str]`): Supported language codes
- **fallback_language** (`str`): Fallback language for missing translations
- **i18n_key_prefix** (`str`): Prefix for i18n translation keys
- **commands** (`Dict[str, CommandDef]`): Command definitions registry
- **profiles** (`Dict[str, ProfileDef]`): User profile definitions
- **scopes** (`List[ScopeDef]`): Command scope definitions
- **menu_button** (`MenuButtonDef`): Menu button configuration

**Example:**
```python
config = CmdsConfig(
    languages=["en", "ru", "es"],
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "help": CommandDef(i18n_key="help.desc"),
    },
    profiles={
        "guest": ProfileDef(include=["start", "help"]),
        "user": ProfileDef(include=["start", "help", "profile"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="guest"),
    ],
)
```

### CommandDef

Command definition with i18n support.

```python
class CommandDef(BaseModel):
    i18n_key: Optional[str] = None
    descriptions: Dict[str, str] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
```

**Fields:**
- **i18n_key** (`str`, optional): i18n key for command description
- **descriptions** (`Dict[str, str]`): Inline descriptions by language
- **tags** (`List[str]`): Command tags for organization

**Description Resolution Order:**
1. i18n_key with translator (if available)
2. Inline descriptions for specific language
3. Fallback to Title Case of command name

**Example:**
```python
# Using i18n key
start_cmd = CommandDef(i18n_key="commands.start.description")

# Using inline descriptions
help_cmd = CommandDef(descriptions={
    "en": "Show help information",
    "ru": "Показать справку",
    "es": "Mostrar ayuda"
})

# Using both (i18n takes precedence)
profile_cmd = CommandDef(
    i18n_key="commands.profile.description",
    descriptions={"en": "View your profile"},
    tags=["user", "profile"]
)
```

### ProfileDef

User profile definition with command inclusion/exclusion.

```python
class ProfileDef(BaseModel):
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
```

**Fields:**
- **include** (`List[str]`): Commands to include in this profile
- **exclude** (`List[str]`): Commands to exclude from this profile

**Logic:**
1. Start with all commands from `include` list
2. Remove any commands that exist in `exclude` list
3. Only include commands that are defined in the commands registry

**Example:**
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

### ScopeDef

Command scope definition for applying profiles to specific contexts.

```python
class ScopeDef(BaseModel):
    scope: ScopeType
    profile: str
    chat_id: Optional[int] = None
    user_id: Optional[int] = None
    languages: List[str] = Field(default_factory=list)
```

**Fields:**
- **scope** (`ScopeType`): Telegram command scope type
- **profile** (`str`): Profile name to apply
- **chat_id** (`int`, optional): Chat ID for chat-specific scopes
- **user_id** (`int`, optional): User ID for user-specific scopes
- **languages** (`List[str]`): Languages for this scope (empty = use global)

**Scope Types:**
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

**Example:**
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

### MenuButtonDef

Menu button configuration.

```python
class MenuButtonDef(BaseModel):
    mode: Literal["commands", "default"] = "commands"
```

**Fields:**
- **mode** (`str`): Menu button mode
  - `"commands"`: Show commands menu button
  - `"default"`: Use default menu button

**Example:**
```python
# Enable commands menu button
menu_button = MenuButtonDef(mode="commands")

# Use default menu button
menu_button = MenuButtonDef(mode="default")
```

## Scope Hierarchy

Scopes are applied in order of specificity (most specific first):

1. **chat_member** - Specific user in specific chat
2. **chat_admins** - All admins in specific chat  
3. **chat** - All users in specific chat
4. **all_chat_admins** - All chat administrators globally
5. **all_group_chats** - All group chats
6. **all_private_chats** - All private chats
7. **default** - Global fallback

**Example:**
```python
scopes = [
    ScopeDef(scope="default", profile="guest"),                    # 7. Global fallback
    ScopeDef(scope="all_private_chats", profile="user"),          # 6. All private chats
    ScopeDef(scope="chat", chat_id=12345, profile="admin"),       # 3. Specific chat
    ScopeDef(scope="chat_member", chat_id=12345, user_id=67890, profile="vip"),  # 1. Specific user
]
```

## Configuration Examples

### Basic Configuration
```python
config = CmdsConfig(
    languages=["en"],
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "help": CommandDef(i18n_key="help.desc"),
    },
    profiles={
        "default": ProfileDef(include=["start", "help"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="default"),
    ],
)
```

### Multi-Language Configuration
```python
config = CmdsConfig(
    languages=["en", "ru", "es", "fr"],
    fallback_language="en",
    commands={
        "start": CommandDef(i18n_key="commands.start"),
        "help": CommandDef(i18n_key="commands.help"),
        "profile": CommandDef(i18n_key="commands.profile"),
    },
    profiles={
        "guest": ProfileDef(include=["start", "help"]),
        "user": ProfileDef(include=["start", "help", "profile"]),
    },
    scopes=[
        ScopeDef(scope="all_private_chats", profile="guest"),
    ],
)
```

### E-commerce Bot Configuration
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

### Admin Bot Configuration
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

## Configuration Validation

### Pydantic Validation

All configuration models use Pydantic for validation:

```python
# This will raise ValidationError
invalid_config = CmdsConfig(
    languages=[],  # Empty languages list
    fallback_language="invalid",  # Not in languages list
)

# This will raise ValidationError
invalid_scope = ScopeDef(
    scope="invalid_scope",  # Not a valid scope type
    profile="nonexistent",  # Profile not defined
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

#### Invalid Scope Parameters
```python
# ❌ Invalid
scope = ScopeDef(
    scope="chat",  # Requires chat_id
    profile="user"
)

# ✅ Valid
scope = ScopeDef(
    scope="chat",
    chat_id=12345,
    profile="user"
)
```

## Configuration Loading

### From pyproject.toml

```toml
[tool.aiogram_cmds]
languages = ["en", "ru", "es"]
fallback_language = "en"
i18n_key_prefix = "cmd"
profile = "default"
menu_button = "commands"
```

### From Code

```python
# Create configuration programmatically
config = CmdsConfig(
    languages=["en", "ru"],
    commands={
        "start": CommandDef(i18n_key="start.desc"),
        "help": CommandDef(i18n_key="help.desc"),
    },
    # ... rest of configuration
)
```

### From JSON/YAML

```python
import json
from aiogram_cmds import CmdsConfig

# Load from JSON
with open("config.json") as f:
    data = json.load(f)
    config = CmdsConfig.model_validate(data)

# Load from YAML
import yaml
with open("config.yaml") as f:
    data = yaml.safe_load(f)
    config = CmdsConfig.model_validate(data)
```

## Best Practices

### 1. Use i18n Keys
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

### 2. Organize Profiles Logically
```python
# ✅ Good - Clear profile hierarchy
profiles = {
    "guest": ProfileDef(include=["start", "help"]),
    "user": ProfileDef(include=["start", "help", "profile"]),
    "admin": ProfileDef(include=["start", "help", "profile", "admin"]),
}

# ❌ Avoid - Unclear profile structure
profiles = {
    "basic": ProfileDef(include=["start"]),
    "advanced": ProfileDef(include=["start", "help", "profile", "admin"]),
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

---

For more information about using configurations, see:
- [Core API](core.md) - How to use configurations with CommandScopeManager
- [Quickstart Guide](../quickstart.md) - Getting started with configurations
