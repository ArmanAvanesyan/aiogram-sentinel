# aiogram-sentinel Examples

This directory contains example implementations demonstrating how to use aiogram-sentinel.

## minimal_bot.py

A complete example bot that demonstrates all aiogram-sentinel features:

### Features Demonstrated

- **Complete Setup**: Shows how to configure aiogram-sentinel with memory backend
- **All Middlewares**: Blocking, Auth, Debouncing, and Throttling
- **Decorators**: `@rate_limit`, `@debounce`, `@require_registered`
- **Hooks**: Rate limit notifications, user resolution, block/unblock events
- **Error Handling**: Proper exception handling and logging

### Commands

- `/start` - Welcome message (rate limited to 3/30s, debounced 1s)
- `/protected` - Requires user registration
- `/spam` - Test rate limiting (1/5s)
- `/help` - Show help information

### Running the Example

1. **Set your bot token:**
   ```bash
   export BOT_TOKEN="your_bot_token_here"
   ```

2. **Run the bot:**
   ```bash
   python examples/minimal_bot.py
   ```

3. **Test the features:**
   - Send `/start` multiple times quickly to see debouncing
   - Send `/spam` multiple times to see rate limiting
   - Try `/protected` to see registration requirement
   - Block/unblock the bot to see membership hooks

### Hook Customization

The example includes comprehensive hook implementations that you can customize:

#### Rate Limit Hook
```python
async def on_rate_limited(event, data, retry_after):
    # Custom logic when user hits rate limit
    # - Send warning message
    # - Log to monitoring
    # - Update statistics
```

#### User Resolution Hook
```python
async def resolve_user(event, data):
    # Custom user validation
    # - Check against blacklist
    # - Validate user permissions
    # - Return user context
```

#### Membership Hooks
```python
async def on_user_blocked(user_id, username, data):
    # Handle user blocking
    # - Log to audit system
    # - Notify admins
    # - Clean up data

async def on_user_unblocked(user_id, username, data):
    # Handle user unblocking
    # - Send welcome message
    # - Restore preferences
    # - Update statistics
```

### Configuration

The example uses a memory backend for simplicity, but you can easily switch to Redis:

```python
config = SentinelConfig(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_prefix="my_bot:",
    # ... other options
)
```

### Next Steps

- Customize the hooks for your specific needs
- Add database integration for user management
- Implement custom rate limiting strategies
- Add monitoring and analytics
- Deploy with Redis backend for production use
