# Error Handling

aiogram-sentinel provides centralized error handling for Telegram/API/domain exceptions with an internal event bus, i18n hooks, RetryAfter synchronization, and optional Sentry integration.

## Overview

The `ErrorHandlingMiddleware` catches exceptions from all other middlewares and handlers, providing:

- **Exception Classification**: Maps Telegram API exceptions to stable i18n keys
- **Domain Classification**: Custom hooks for application-specific exceptions
- **Internationalization**: Pluggable locale and message resolvers
- **RetryAfter Sync**: Automatically syncs Telegram rate limits with internal cooldowns
- **Event Emission**: Publishes error events to an internal event bus
- **Friendly Messages**: Sends localized error messages to users
- **Resilience**: Never crashes, even if error handling components fail

## Quick Start

```python
from aiogram_sentinel import Sentinel, SentinelConfig, ErrorConfig

# Configure error handling
error_config = ErrorConfig(
    use_friendly_messages=True,
    show_alert_for_callbacks=True,
)

# Setup with error handling
config = SentinelConfig(backend="memory")
router, infra = await Sentinel.setup(dp, config, error_config=error_config)
```

## Configuration

### ErrorConfig Options

```python
@dataclass
class ErrorConfig:
    use_friendly_messages: bool = True
    domain_classifier: Callable[[Exception], str | None] | None = None
    message_resolver: Callable[[str, str], str] | None = None
    locale_resolver: Callable[[TelegramObject, dict], str] | None = None
    on_error: Callable[[TelegramObject, Exception, dict], Awaitable[None]] | None = None
    sync_retry_after: bool = True
    respond_strategy: str = "answer"  # "answer", "reply", "none"
    show_alert_for_callbacks: bool = False
    send_strategy: Callable[[TelegramObject, dict, str], Awaitable[None]] | None = None
```

### Basic Configuration

```python
# Minimal configuration
error_config = ErrorConfig()

# Disable friendly messages
error_config = ErrorConfig(use_friendly_messages=False)

# Custom callback alert behavior
error_config = ErrorConfig(show_alert_for_callbacks=True)
```

## Exception Classification

### Telegram API Exceptions

The middleware automatically classifies Telegram API exceptions:

| Exception | i18n Key |
|-----------|----------|
| `BadRequest` | `error_telegram_badrequest` |
| `Forbidden` | `error_telegram_forbidden` |
| `Conflict` | `error_telegram_conflict` |
| `RetryAfter` | `error_telegram_retry_after` |
| `ServerError` | `error_telegram_server` |
| `TelegramAPIError` | `error_telegram_generic` |

### Domain Classification

Use the `domain_classifier` hook to handle application-specific exceptions:

```python
def classify_domain_error(exc: Exception) -> str | None:
    if isinstance(exc, ValidationError):
        return "error_validation"
    elif isinstance(exc, PermissionError):
        return "error_permission"
    elif isinstance(exc, NotFoundError):
        return "error_not_found"
    return None  # Fallback to system error

error_config = ErrorConfig(domain_classifier=classify_domain_error)
```

### Fallback Behavior

If no classification is found, the middleware falls back to:
- `error_sentinel_generic` for aiogram-sentinel exceptions
- `error_unexpected_system` for all other exceptions

## Internationalization

### Locale Resolution

Use the `locale_resolver` hook to determine the user's locale:

```python
def resolve_locale(event: TelegramObject, data: dict) -> str:
    # Get locale from user data
    user = getattr(event, 'from_user', None)
    if user and hasattr(user, 'language_code'):
        return user.language_code or 'en'
    
    # Get locale from database
    user_id = getattr(user, 'id', None)
    if user_id:
        return get_user_locale(user_id) or 'en'
    
    return 'en'  # Default fallback

error_config = ErrorConfig(locale_resolver=resolve_locale)
```

### Message Resolution

Use the `message_resolver` hook to translate error keys to user-friendly messages:

```python
def resolve_message(key: str, locale: str) -> str:
    # Use your i18n system
    return i18n.translate(key, locale)

error_config = ErrorConfig(message_resolver=resolve_message)
```

### Default Behavior

If no resolvers are provided:
- Locale defaults to `"en"`
- Message defaults to the error key itself

## RetryAfter Synchronization

When `sync_retry_after=True` (default), the middleware automatically syncs Telegram's `RetryAfter` exceptions with internal cooldowns:

```python
# RetryAfter exception with 5.5 seconds
raise RetryAfter(retry_after=5.5)

# Automatically creates internal cooldown for 6 seconds (ceil(5.5))
# Uses KeyBuilder with namespace="retryafter" and appropriate scope
```

This ensures that subsequent requests are properly throttled during the Telegram-imposed cooldown period.

## Message Sending

### Default Strategy

The middleware automatically detects the event type and sends appropriate responses:

- **CallbackQuery**: Uses `answer(text, show_alert=config.show_alert_for_callbacks)`
- **Message**: Uses `reply(text, disable_notification=True)`

### Custom Send Strategy

Override the default behavior with a custom `send_strategy`:

```python
async def custom_send_strategy(event: TelegramObject, data: dict, text: str) -> None:
    # Custom logic for sending error messages
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
    elif isinstance(event, Message):
        await event.answer(text)  # Use answer instead of reply
    # Handle other event types...

error_config = ErrorConfig(send_strategy=custom_send_strategy)
```

### Error Resilience

The middleware handles send failures gracefully:
- Catches `MessageNotModified` and `CantInitiateConversation`
- Logs send failures without crashing
- Continues with other error handling steps

## Event Bus

### ErrorEvent Structure

```python
@dataclass
class ErrorEvent:
    error_type: str           # i18n key
    error_message: str        # Raw exception message
    event_type: str          # "message", "callback", etc.
    user_id: int | None      # User ID
    chat_id: int | None      # Chat ID
    locale: str              # Resolved locale
    retry_after: float | None # RetryAfter seconds (if applicable)
```

### Subscribing to Events

```python
from aiogram_sentinel.events import ErrorEvent, events

async def handle_error_event(event: ErrorEvent) -> None:
    # Log to external monitoring
    logger.error(f"Error: {event.error_type} for user {event.user_id}")
    
    # Send to analytics
    analytics.track_error(event.error_type, event.user_id)

# Subscribe to error events
events.subscribe(ErrorEvent, handle_error_event)
```

## Error Hooks

### on_error Hook

Use the `on_error` hook for custom error handling logic:

```python
async def custom_error_handler(event: TelegramObject, exc: Exception, data: dict) -> None:
    # Log detailed error information
    logger.exception(f"Handler error: {exc}")
    
    # Update error statistics
    stats.increment_error_count(type(exc).__name__)
    
    # Send notification to admins
    await notify_admins(f"Error in bot: {exc}")

error_config = ErrorConfig(on_error=custom_error_handler)
```

The hook is called after all other error handling steps and never raises exceptions.

## Sentry Integration

### Installation

```bash
pip install aiogram-sentinel[sentry]
```

### Basic Setup

```python
from aiogram_sentinel.integrations.sentry import use_sentry

# Configure Sentry integration
use_sentry(
    dsn="your-sentry-dsn",
    environment="production",
    send_breadcrumbs=True,
    capture_errors=True,
)
```

### Advanced Configuration

```python
def user_context_resolver(event: TelegramObject, data: dict) -> dict:
    user = getattr(event, 'from_user', None)
    return {
        'id': getattr(user, 'id', None),
        'username': getattr(user, 'username', None),
    }

def scrub_sensitive_data(event, hint):
    # Remove sensitive data from Sentry events
    if 'password' in str(event):
        return None
    return event

use_sentry(
    dsn="your-sentry-dsn",
    environment="production",
    send_breadcrumbs=True,
    capture_errors=True,
    user_context_resolver=user_context_resolver,
    scrubber=scrub_sensitive_data,
)
```

## Middleware Order

The `ErrorHandlingMiddleware` is installed as the outermost middleware to catch exceptions from all other middlewares:

```
ErrorHandlingMiddleware (OUTERMOST - catches all)
  → PolicyResolverMiddleware
    → DebounceMiddleware
      → ThrottlingMiddleware
        → Handlers
```

## Migration from Custom Error Middleware

### Before (Custom Middleware)

```python
@dp.message.middleware()
async def error_middleware(handler, event, data):
    try:
        return await handler(event, data)
    except Exception as exc:
        logger.exception(f"Handler error: {exc}")
        await event.answer("An error occurred")
        return None
```

### After (aiogram-sentinel)

```python
from aiogram_sentinel import ErrorConfig

error_config = ErrorConfig(
    use_friendly_messages=True,
    on_error=lambda event, exc, data: logger.exception(f"Handler error: {exc}")
)

router, infra = await Sentinel.setup(dp, config, error_config=error_config)
```

## Best Practices

### 1. Use Domain Classification

Always provide a `domain_classifier` for application-specific exceptions:

```python
def classify_errors(exc: Exception) -> str | None:
    if isinstance(exc, ValidationError):
        return "error_validation"
    elif isinstance(exc, DatabaseError):
        return "error_database"
    return None
```

### 2. Implement Proper i18n

Use proper internationalization for user-facing messages:

```python
def resolve_message(key: str, locale: str) -> str:
    messages = {
        'en': {
            'error_validation': 'Please check your input and try again.',
            'error_database': 'Service temporarily unavailable.',
        },
        'ru': {
            'error_validation': 'Проверьте ввод и попробуйте снова.',
            'error_database': 'Сервис временно недоступен.',
        }
    }
    return messages.get(locale, messages['en']).get(key, key)
```

### 3. Monitor Error Events

Subscribe to error events for monitoring and analytics:

```python
async def monitor_errors(event: ErrorEvent) -> None:
    # Track error rates
    metrics.increment(f"errors.{event.error_type}")
    
    # Alert on critical errors
    if event.error_type == "error_database":
        await alert_admins("Database errors detected")
```

### 4. Use Sentry for Production

Enable Sentry integration in production for comprehensive error tracking:

```python
if config.environment == "production":
    use_sentry(
        dsn=config.sentry_dsn,
        environment=config.environment,
        capture_errors=True,
    )
```

## Examples

### Complete Example

```python
import logging
from aiogram_sentinel import Sentinel, SentinelConfig, ErrorConfig
from aiogram_sentinel.events import ErrorEvent, events

logger = logging.getLogger(__name__)

# Domain classification
def classify_errors(exc: Exception) -> str | None:
    if isinstance(exc, ValueError):
        return "error_validation"
    elif isinstance(exc, PermissionError):
        return "error_permission"
    return None

# Locale resolution
def resolve_locale(event, data) -> str:
    user = getattr(event, 'from_user', None)
    return getattr(user, 'language_code', 'en') or 'en'

# Message resolution
def resolve_message(key: str, locale: str) -> str:
    messages = {
        'error_validation': 'Please check your input.',
        'error_permission': 'You do not have permission.',
    }
    return messages.get(key, key)

# Error monitoring
async def monitor_errors(event: ErrorEvent) -> None:
    logger.error(f"Error: {event.error_type} for user {event.user_id}")

# Configure error handling
error_config = ErrorConfig(
    domain_classifier=classify_errors,
    locale_resolver=resolve_locale,
    message_resolver=resolve_message,
    use_friendly_messages=True,
    show_alert_for_callbacks=True,
)

# Subscribe to events
events.subscribe(ErrorEvent, monitor_errors)

# Setup
config = SentinelConfig(backend="redis", redis_url="redis://localhost:6379")
router, infra = await Sentinel.setup(dp, config, error_config=error_config)
```

This provides comprehensive error handling with classification, internationalization, monitoring, and user-friendly messages.
