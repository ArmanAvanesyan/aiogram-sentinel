# aiogram-sentinel Examples

This directory contains example implementations demonstrating how to use aiogram-sentinel.

## minimal_bot.py

A complete example bot that demonstrates aiogram-sentinel core features:

### Features Demonstrated

- **Complete Setup**: Shows how to configure aiogram-sentinel with memory backend
- **Core Middlewares**: Debouncing and Throttling
- **Decorators**: `@rate_limit`, `@debounce`
- **Hooks**: Rate limit notifications
- **Error Handling**: Proper exception handling and logging

### Commands

- `/start` - Welcome message (rate limited to 3/30s, debounced 1s)
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

### Hook Customization

The example includes a rate limit hook implementation that you can customize:

#### Rate Limit Hook
```python
async def on_rate_limited(event, data, retry_after):
    # Custom logic when user hits rate limit
    # - Send warning message
    # - Log to monitoring
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
- Implement custom rate limiting strategies
- Add monitoring and analytics
- Deploy with Redis backend for production use
