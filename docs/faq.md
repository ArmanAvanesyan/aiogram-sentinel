# Frequently Asked Questions

This document answers common questions about aiogram-cmds.

## 🤔 General Questions

### What is aiogram-cmds?

aiogram-cmds is a command management library for aiogram v3 that helps you manage Telegram bot commands with i18n support, user profiles, and dynamic scopes.

### Why should I use aiogram-cmds?

- **Simplified Command Management**: No need to manually manage command scopes
- **i18n Support**: Built-in support for multiple languages
- **User Profiles**: Dynamic command sets based on user status
- **Production Ready**: Comprehensive testing and documentation
- **Type Safe**: Full type hints and validation

### Is aiogram-cmds compatible with aiogram v2?

No, aiogram-cmds is designed specifically for aiogram v3. For aiogram v2, you'll need to use the built-in command management features.

### What Python versions are supported?

aiogram-cmds supports Python 3.10+ (3.10, 3.11, 3.12, 3.13).

## 🚀 Getting Started

### How do I install aiogram-cmds?

```bash
pip install aiogram-cmds
```

For Redis support:
```bash
pip install aiogram-cmds[redis]
```

### What's the quickest way to get started?

Use auto-setup:

```python
from aiogram_cmds.auto_setup import setup_commands_auto

manager = await setup_commands_auto(bot)
```

### Do I need to configure anything?

No! aiogram-cmds works out of the box with sensible defaults. You can customize later as needed.

## ⚙️ Configuration

### How do I add multiple languages?

```python
config = CmdsConfig(
    languages=["en", "ru", "es"],
    fallback_language="en",
    # ... rest of configuration
)
```

### How do I create user-specific commands?

Use profiles and profile resolvers:

```python
profiles = {
    "guest": ProfileDef(include=["start", "help"]),
    "user": ProfileDef(include=["start", "help", "profile"]),
    "admin": ProfileDef(include=["start", "help", "profile", "admin"]),
}

def profile_resolver(flags: Flags) -> str:
    if flags.is_admin:
        return "admin"
    elif flags.is_registered:
        return "user"
    return "guest"
```

### How do I update commands dynamically?

```python
await manager.update_user_commands(
    user_id=12345,
    is_registered=True,
    has_vehicle=False,
    user_language="en"
)
```

### Can I use configuration files?

Yes! Create `pyproject.toml`:

```toml
[tool.aiogram_cmds]
languages = ["en", "ru"]
fallback_language = "en"
i18n_key_prefix = "cmd"
```

Then load it:

```python
from aiogram_cmds import load_settings
settings = load_settings()
```

## 🌍 i18n and Translations

### How do I integrate with aiogram i18n?

```python
from aiogram_cmds import build_translator_from_i18n

translator = build_translator_from_i18n(i18n_instance)
manager = CommandScopeManager(bot, translator=translator)
```

### What translation key pattern should I use?

The default pattern is `{prefix}.{command}.desc`:

```
cmd.start.desc → "Start the bot"
cmd.help.desc → "Show help information"
```

### How do I handle missing translations?

aiogram-cmds automatically falls back to:
1. Fallback language translation
2. Title Case of command name
3. "Command" as final fallback

### Can I use custom translation keys?

Yes! Set the `i18n_key` in CommandDef:

```python
commands = {
    "start": CommandDef(i18n_key="commands.start.description"),
    "help": CommandDef(i18n_key="menu.help.tooltip"),
}
```

## 🎯 Profiles and Scopes

### What are profiles?

Profiles are named sets of commands that can be applied to users based on their status or permissions.

### How do scopes work?

Scopes define where and how commands are applied. They follow Telegram's command scope hierarchy:

1. `chat_member` - Most specific
2. `chat_admins`
3. `chat`
4. `all_chat_admins`
5. `all_group_chats`
6. `all_private_chats`
7. `default` - Least specific

### Can I have different commands for different chats?

Yes! Use chat-specific scopes:

```python
scopes = [
    ScopeDef(scope="all_private_chats", profile="user"),
    ScopeDef(scope="chat", chat_id=12345, profile="admin"),
]
```

### How do I create admin-only commands?

Create an admin profile and apply it to specific users or chats:

```python
profiles = {
    "user": ProfileDef(include=["start", "help"]),
    "admin": ProfileDef(include=["start", "help", "admin", "ban"]),
}

scopes = [
    ScopeDef(scope="chat_member", chat_id=12345, user_id=67890, profile="admin"),
]
```

## 🔧 Troubleshooting

### Commands don't appear in Telegram

1. Make sure you call `await manager.setup_all()`
2. Check that your bot token is valid
3. Verify command names are valid (lowercase, letters, numbers, underscores only)
4. Check the logs for error messages

### i18n translations don't work

1. Ensure your i18n instance is properly configured
2. Check that translation keys exist in your locale files
3. Verify the `i18n_key_prefix` matches your translation key structure
4. Test with a simple translator first

### Profile resolver not working

1. Make sure your profile resolver returns valid profile names
2. Check that profiles are defined in your configuration
3. Verify that the profile includes/excludes valid command names
4. Add logging to debug profile resolution

### Commands not updating dynamically

1. Make sure to call `update_user_commands()` after state changes
2. Check that your profile resolver is working correctly
3. Verify that the new profile has the expected commands
4. Check the logs for any errors

### Import errors

```bash
# Make sure aiogram-cmds is installed
pip install aiogram-cmds

# Check installation
python -c "import aiogram_cmds; print(aiogram_cmds.__version__)"
```

### Bot not responding

1. Check your bot token
2. Make sure the bot is running
3. Check logs for error messages
4. Verify your message handlers are registered

## 🚀 Performance

### Is aiogram-cmds fast?

Yes! aiogram-cmds is optimized for performance:
- Efficient command building
- Minimal API calls to Telegram
- Cached profile resolutions
- Batch operations where possible

### How do I optimize for large user bases?

1. Implement application-owned coordination for multiple workers
2. Cache profile resolutions
3. Batch command updates
4. Use appropriate scope hierarchy
5. Monitor performance metrics

### Can I use it with multiple workers?

Applications can use multiple workers, but this package does not coordinate
concurrent command updates. The optional `redis` extra installs a client only.
Applications must implement their own shared state, locking and recovery if
needed; command scopes may otherwise be overwritten by competing workers.

## 🔒 Security

### Is aiogram-cmds secure?

Yes! aiogram-cmds follows security best practices:
- Input validation with Pydantic
- No sensitive data in logs
- Graceful error handling
- Type safety with strict type checking

### How do I handle user permissions securely?

1. Validate user permissions in your profile resolver
2. Use proper scope hierarchy
3. Don't expose sensitive commands to unauthorized users
4. Implement proper authentication

## 🧪 Testing

### How do I test my configuration?

```python
def test_configuration():
    config = CmdsConfig(...)
    # Configuration is validated automatically
    assert config.languages == ["en", "ru"]
```

### How do I test profile resolution?

```python
def test_profile_resolver():
    resolver = my_profile_resolver
    flags = Flags(is_registered=True, has_vehicle=False)
    profile = resolver(flags)
    assert profile == "user"
```

### How do I test command updates?

```python
async def test_command_updates():
    manager = CommandScopeManager(bot)
    await manager.update_user_commands(
        user_id=12345,
        is_registered=True,
        has_vehicle=False
    )
    # Commands should be updated
```

## 🤝 Contributing

### How do I contribute?

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

### What are the coding standards?

- Follow PEP 8
- Use type hints
- Write docstrings
- Add tests for new features
- Update documentation

### How do I run the tests?

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=src/aiogram_cmds
```

## 📚 Documentation

### Where can I find more documentation?

- [Quickstart Guide](quickstart.md) - Get started in 5 minutes
- [API Reference](api/core.md) - Complete API documentation
- [Tutorials](tutorials/basic-setup.md) - Step-by-step guides
- [Examples](https://github.com/ArmanAvanesyan/aiogram-cmds/tree/main/examples) - Working bot examples

### How do I report documentation issues?

Create an issue on GitHub or submit a pull request with improvements.

## 🆘 Getting Help

### Where can I get help?

- [GitHub Discussions](https://github.com/ArmanAvanesyan/aiogram-cmds/discussions) - Community help
- [GitHub Issues](https://github.com/ArmanAvanesyan/aiogram-cmds/issues) - Bug reports
- [Documentation](https://armanavanesyan.github.io/aiogram-cmds/) - Complete guides

### How do I report bugs?

1. Check existing issues first
2. Create a new issue with:
   - Clear description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details

### How do I request features?

1. Check existing feature requests
2. Create a new issue with:
   - Clear description of the feature
   - Use case and benefits
   - Implementation suggestions (if any)

---

**Still have questions?** Check out our [GitHub Discussions](https://github.com/ArmanAvanesyan/aiogram-cmds/discussions) or [create an issue](https://github.com/ArmanAvanesyan/aiogram-cmds/issues)!
