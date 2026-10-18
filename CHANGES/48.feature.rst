Error Handling Middleware with Domain/i18n Hooks

**New Features:**

* **ErrorHandlingMiddleware**: Centralized error handling for Telegram/API/domain exceptions with configurable hooks and event emission
* **Internal Event Bus**: Simple asyncio pub/sub system (`SentinelEvents`) for error events and future observability features
* **Exception Classification**: Automatic mapping of Telegram API exceptions to stable i18n keys with domain classifier hooks
* **Internationalization Support**: Pluggable locale and message resolvers for multi-language error messages
* **RetryAfter Synchronization**: Automatic sync of Telegram rate limits with internal cooldowns using KeyBuilder
* **Friendly Message Sending**: Context-aware message delivery (CallbackQuery vs Message) with error resilience
* **Sentry Integration**: Optional Sentry integration with breadcrumbs, exception capture, and user context resolution
* **Error Hooks**: Configurable `on_error` hook for custom error handling logic that never raises exceptions

**API Changes:**

* **New Public API**: Added `ErrorConfig`, `ErrorEvent`, `ErrorHandlingMiddleware` to public exports
* **Sentinel.setup() Enhancement**: Added optional `error_config` parameter for error handling configuration
* **New Method**: Added `Sentinel.use_errors(error_config)` for convenient error handling setup
* **Middleware Order**: `ErrorHandlingMiddleware` now runs as outermost middleware to catch all exceptions
* **Optional Dependencies**: Added `[sentry]` extra with `sentry-sdk>=1.40.0` for Sentry integration

**Key Benefits:**

* **Centralized Error Handling**: Single point for all error processing with consistent behavior
* **Resilient Design**: Never crashes, even if error handling components fail
* **Observability Ready**: Event bus enables easy integration with monitoring and analytics systems
* **User-Friendly**: Automatic localized error messages with context-aware delivery
* **Production Ready**: Optional Sentry integration for comprehensive error tracking
* **Extensible**: Pluggable hooks for domain classification, i18n, and custom error handling

**Telegram Exception Mapping:**

* `BadRequest` → `error_telegram_badrequest`
* `Forbidden` → `error_telegram_forbidden`
* `Conflict` → `error_telegram_conflict`
* `RetryAfter` → `error_telegram_retry_after` (with cooldown sync)
* `ServerError` → `error_telegram_server`
* `TelegramAPIError` → `error_telegram_generic`

**Usage Examples:**

* Basic setup with friendly messages:
  ```python
  error_config = ErrorConfig(use_friendly_messages=True)
  router, infra = await Sentinel.setup(dp, config, error_config=error_config)
  ```

* Domain classification with i18n:
  ```python
  def classify_errors(exc: Exception) -> str | None:
      if isinstance(exc, ValidationError):
          return "error_validation"
      return None
  
  error_config = ErrorConfig(
      domain_classifier=classify_errors,
      locale_resolver=lambda event, data: get_user_locale(event.from_user.id),
      message_resolver=lambda key, locale: i18n.translate(key, locale),
  )
  ```

* Sentry integration:
  ```python
  from aiogram_sentinel.integrations.sentry import use_sentry
  
  use_sentry(dsn="your-dsn", capture_errors=True)
  ```

* Event monitoring:
  ```python
  from aiogram_sentinel.events import ErrorEvent, events
  
  async def monitor_errors(event: ErrorEvent) -> None:
      metrics.increment(f"errors.{event.error_type}")
  
  events.subscribe(ErrorEvent, monitor_errors)
  ```

**Technical Details:**

* **Event Bus**: Fire-and-forget async pub/sub with `asyncio.gather(*, return_exceptions=True)` for resilience
* **RetryAfter Sync**: Uses `KeyBuilder(namespace="retryafter")` with `ceil(retry_after_seconds)` TTL
* **Message Sending**: Default strategy uses `answer()` for callbacks, `reply()` for messages with `disable_notification=True`
* **Error Resilience**: All hooks wrapped in try/except, send failures logged but don't crash
* **Middleware Integration**: Error middleware installed outermost to catch exceptions from all other middlewares
* **Sentry Integration**: Optional dependency with guarded imports and comprehensive configuration options
