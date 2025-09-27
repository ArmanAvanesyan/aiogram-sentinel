# Hooks

This document describes all available hooks in aiogram-sentinel and how to use them for customization.

## Overview

Hooks are async functions that allow you to customize aiogram-sentinel behavior at specific points in the event processing pipeline. They provide a way to:

- **Customize responses**: Send custom messages when events occur
- **Integrate with external systems**: Log to databases, send notifications
- **Implement business logic**: Custom validation, user management
- **Monitor and analytics**: Track usage patterns, performance metrics

## Hook Types

### 1. Rate Limiting Hooks

#### `on_rate_limited`

Called when a user exceeds their rate limit.

**Signature:**
```python
async def on_rate_limited(
    event: TelegramObject,
    data: Dict[str, Any],
    retry_after: float
) -> None:
    """Handle rate limit exceeded event."""
```

**Parameters:**
- `event`: The original Telegram event (Message, CallbackQuery, etc.)
- `data`: Middleware data dictionary
- `retry_after`: Seconds until the user can try again

**Example:**
```python
async def on_rate_limited(event, data, retry_after):
    """Send a friendly rate limit message."""
    if isinstance(event, Message):
        await event.answer(
            f"⏰ You're sending messages too quickly!\n"
            f"Please wait {retry_after:.1f} seconds before trying again.",
            show_alert=True
        )
    
    # Log to monitoring system
    logger.warning(f"Rate limit exceeded for user {event.from_user.id}")
    
    # Update user statistics
    await update_user_stats(event.from_user.id, "rate_limited")
```

**Usage:**
```python
router, backends = Sentinel.setup(
    dp, config,
    on_rate_limited=on_rate_limited
)
```

### 2. User Resolution Hooks

#### `resolve_user`

Called during authentication to validate and enrich user data.

**Signature:**
```python
async def resolve_user(
    event: TelegramObject,
    data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Resolve and validate user information."""
```

**Parameters:**
- `event`: The original Telegram event
- `data`: Middleware data dictionary

**Returns:**
- `Dict[str, Any]`: User context data (continues processing)
- `None`: Veto the request (stops processing)

**Example:**
```python
async def resolve_user(event, data):
    """Custom user validation and enrichment."""
    if not hasattr(event, "from_user") or not event.from_user:
        return None
    
    user = event.from_user
    
    # Block bot users
    if user.is_bot:
        logger.info(f"Blocking bot user: {user.id}")
        return None
    
    # Check against blacklist
    if await is_user_blacklisted(user.id):
        logger.info(f"Blocking blacklisted user: {user.id}")
        return None
    
    # Check user permissions
    user_role = await get_user_role(user.id)
    if user_role == "banned":
        return None
    
    # Return enriched user context
    return {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_bot": user.is_bot,
        "is_premium": getattr(user, "is_premium", False),
        "language_code": user.language_code,
        "role": user_role,
        "permissions": await get_user_permissions(user.id),
        "last_seen": time.time(),
    }
```

**Usage:**
```python
router, backends = Sentinel.setup(
    dp, config,
    resolve_user=resolve_user
)
```

### 3. Membership Hooks

#### `on_block`

Called when a user is blocked (kicked from the bot).

**Signature:**
```python
async def on_block(
    user_id: int,
    username: str,
    data: Dict[str, Any]
) -> None:
    """Handle user blocking event."""
```

**Parameters:**
- `user_id`: The blocked user's ID
- `username`: The blocked user's username (may be empty)
- `data`: Event data including status transitions

**Example:**
```python
async def on_block(user_id, username, data):
    """Handle user blocking with custom logic."""
    logger.info(f"User blocked: {username} (ID: {user_id})")
    
    # Log to audit system
    await audit_log.create({
        "event": "user_blocked",
        "user_id": user_id,
        "username": username,
        "old_status": data.get("old_status"),
        "new_status": data.get("new_status"),
        "timestamp": time.time(),
    })
    
    # Notify administrators
    await notify_admins(
        f"🔴 User blocked: {username} (ID: {user_id})\n"
        f"Status: {data.get('old_status')} → {data.get('new_status')}"
    )
    
    # Clean up user data
    await cleanup_user_data(user_id)
    
    # Update statistics
    await update_stats("users_blocked", 1)
```

#### `on_unblock`

Called when a user is unblocked (rejoins the bot).

**Signature:**
```python
async def on_unblock(
    user_id: int,
    username: str,
    data: Dict[str, Any]
) -> None:
    """Handle user unblocking event."""
```

**Parameters:**
- `user_id`: The unblocked user's ID
- `username`: The unblocked user's username (may be empty)
- `data`: Event data including status transitions

**Example:**
```python
async def on_unblock(user_id, username, data):
    """Handle user unblocking with welcome back logic."""
    logger.info(f"User unblocked: {username} (ID: {user_id})")
    
    # Log to audit system
    await audit_log.create({
        "event": "user_unblocked",
        "user_id": user_id,
        "username": username,
        "old_status": data.get("old_status"),
        "new_status": data.get("new_status"),
        "timestamp": time.time(),
    })
    
    # Send welcome back message
    try:
        await bot.send_message(
            user_id,
            "👋 Welcome back! You've been unblocked and can use the bot again."
        )
    except Exception as e:
        logger.error(f"Failed to send welcome message: {e}")
    
    # Restore user preferences
    await restore_user_preferences(user_id)
    
    # Update statistics
    await update_stats("users_unblocked", 1)
```

**Usage:**
```python
router, backends = Sentinel.setup(
    dp, config,
    on_block=on_block,
    on_unblock=on_unblock
)
```

## Hook Implementation Patterns

### 1. Error Handling

Always wrap hook implementations in try-catch blocks to prevent middleware failures:

```python
async def safe_hook(event, data, retry_after):
    """Hook with proper error handling."""
    try:
        # Your hook logic here
        await process_event(event, data)
    except Exception as e:
        logger.error(f"Hook failed: {e}")
        # Don't re-raise - let middleware continue
```

### 2. Async Operations

Hooks are async functions, so you can perform async operations:

```python
async def database_hook(event, data):
    """Hook that interacts with databases."""
    # Database operations
    await db.users.update_last_seen(event.from_user.id)
    
    # External API calls
    response = await http_client.post("/api/events", {
        "user_id": event.from_user.id,
        "event_type": "message_received"
    })
    
    # File operations
    await log_to_file("user_activity.log", f"User {event.from_user.id} sent message")
```

### 3. Conditional Logic

Use conditional logic to handle different event types:

```python
async def smart_hook(event, data, retry_after):
    """Hook that handles different event types."""
    if isinstance(event, Message):
        # Handle message events
        await handle_message_event(event, data)
    elif isinstance(event, CallbackQuery):
        # Handle callback events
        await handle_callback_event(event, data)
    else:
        # Handle other event types
        await handle_other_event(event, data)
```

### 4. Data Enrichment

Enrich the data dictionary with additional information:

```python
async def enrichment_hook(event, data):
    """Hook that enriches event data."""
    # Add custom data
    data["custom_field"] = "custom_value"
    data["timestamp"] = time.time()
    data["user_agent"] = await get_user_agent(event.from_user.id)
    
    # Modify existing data
    if "user_context" in data:
        data["user_context"]["enriched"] = True
```

## Hook Configuration

### Basic Setup

```python
# Define your hooks
async def my_rate_limit_hook(event, data, retry_after):
    # Your logic here
    pass

async def my_user_resolver(event, data):
    # Your logic here
    return {"user_id": event.from_user.id}

async def my_block_hook(user_id, username, data):
    # Your logic here
    pass

# Configure with hooks
router, backends = Sentinel.setup(
    dp, config,
    on_rate_limited=my_rate_limit_hook,
    resolve_user=my_user_resolver,
    on_block=my_block_hook,
)
```

### Advanced Configuration

```python
# Create hook classes for better organization
class MyHooks:
    def __init__(self, db, logger, bot):
        self.db = db
        self.logger = logger
        self.bot = bot
    
    async def on_rate_limited(self, event, data, retry_after):
        # Class-based hook implementation
        await self.db.log_rate_limit(event.from_user.id, retry_after)
        self.logger.warning(f"Rate limit: {event.from_user.id}")
    
    async def resolve_user(self, event, data):
        # Class-based user resolution
        user_data = await self.db.get_user(event.from_user.id)
        return user_data
    
    async def on_block(self, user_id, username, data):
        # Class-based block handling
        await self.db.block_user(user_id)
        await self.bot.send_message(ADMIN_CHAT, f"User {username} blocked")

# Use class-based hooks
hooks = MyHooks(database, logger, bot)
router, backends = Sentinel.setup(
    dp, config,
    on_rate_limited=hooks.on_rate_limited,
    resolve_user=hooks.resolve_user,
    on_block=hooks.on_block,
)
```

## Best Practices

### 1. Performance

- **Keep hooks fast**: Avoid blocking operations
- **Use async**: Leverage async/await for I/O operations
- **Cache data**: Cache frequently accessed data
- **Batch operations**: Group multiple operations together

### 2. Reliability

- **Error handling**: Always wrap hooks in try-catch
- **Timeout handling**: Set timeouts for external calls
- **Fallback logic**: Provide fallbacks for failed operations
- **Logging**: Log all hook activities

### 3. Security

- **Input validation**: Validate all inputs
- **Sanitization**: Sanitize user data
- **Access control**: Check permissions before operations
- **Audit logging**: Log security-relevant events

### 4. Monitoring

- **Metrics**: Track hook performance and usage
- **Alerting**: Set up alerts for hook failures
- **Debugging**: Include debug information in logs
- **Testing**: Test hooks thoroughly

## Common Use Cases

### 1. User Management

```python
async def user_management_hooks(event, data):
    """Comprehensive user management hooks."""
    
    # Rate limit hook
    async def on_rate_limited(event, data, retry_after):
        await user_service.log_rate_limit(event.from_user.id)
        await notification_service.notify_user(event.from_user.id, "rate_limited")
    
    # User resolution
    async def resolve_user(event, data):
        user = await user_service.get_or_create_user(event.from_user)
        if user.is_banned:
            return None
        return user.to_dict()
    
    # Block handling
    async def on_block(user_id, username, data):
        await user_service.ban_user(user_id, "bot_blocked")
        await admin_service.notify_block(user_id, username)
    
    return {
        "on_rate_limited": on_rate_limited,
        "resolve_user": resolve_user,
        "on_block": on_block,
    }
```

### 2. Analytics and Monitoring

```python
async def analytics_hooks(event, data):
    """Analytics and monitoring hooks."""
    
    async def on_rate_limited(event, data, retry_after):
        await analytics.track("rate_limit_exceeded", {
            "user_id": event.from_user.id,
            "retry_after": retry_after,
        })
    
    async def resolve_user(event, data):
        await analytics.track("user_interaction", {
            "user_id": event.from_user.id,
            "event_type": type(event).__name__,
        })
        return {"user_id": event.from_user.id}
    
    return {
        "on_rate_limited": on_rate_limited,
        "resolve_user": resolve_user,
    }
```

### 3. Integration with External Systems

```python
async def external_integration_hooks(event, data):
    """Integration with external systems."""
    
    async def on_rate_limited(event, data, retry_after):
        # Send to external monitoring
        await external_monitoring.alert("rate_limit", {
            "user_id": event.from_user.id,
            "severity": "warning",
        })
        
        # Update CRM system
        await crm.update_user_status(event.from_user.id, "rate_limited")
    
    async def resolve_user(event, data):
        # Check against external blacklist
        if await external_blacklist.is_blacklisted(event.from_user.id):
            return None
        
        # Sync with external user database
        await external_db.sync_user(event.from_user)
        
        return {"user_id": event.from_user.id}
    
    return {
        "on_rate_limited": on_rate_limited,
        "resolve_user": resolve_user,
    }
```

## Troubleshooting

### Common Issues

1. **Hook not called**: Check hook registration and middleware order
2. **Hook failures**: Ensure proper error handling
3. **Performance issues**: Optimize hook implementations
4. **Data not available**: Check middleware data dictionary

### Debugging

```python
async def debug_hook(event, data, retry_after):
    """Debug hook to troubleshoot issues."""
    logger.debug(f"Hook called with event: {type(event).__name__}")
    logger.debug(f"Data keys: {list(data.keys())}")
    logger.debug(f"Retry after: {retry_after}")
    
    # Your actual hook logic here
    pass
```

### Testing Hooks

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_rate_limit_hook():
    """Test rate limit hook."""
    hook = AsyncMock()
    event = Mock()
    data = {}
    retry_after = 5.0
    
    await hook(event, data, retry_after)
    
    hook.assert_called_once_with(event, data, retry_after)
```
