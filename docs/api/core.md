# Core API

## Main Classes

::: aiogram_sentinel.Sentinel
    options:
      show_source: true
      members:
        - __init__
        - middleware
        - config
        - storage
        - rate_limiter_backend
        - debounce_backend
        - blocklist_backend
        - user_repo

::: aiogram_sentinel.SentinelConfig
    options:
      show_source: true
      members:
        - __init__
        - throttling_default_max
        - throttling_default_per_seconds
        - debounce_default_window
        - blocklist_enabled
        - auth_required

## Middleware

::: aiogram_sentinel.middlewares.ThrottlingMiddleware
    options:
      show_source: true

::: aiogram_sentinel.middlewares.DebounceMiddleware
    options:
      show_source: true

::: aiogram_sentinel.middlewares.AuthMiddleware
    options:
      show_source: true

::: aiogram_sentinel.middlewares.BlockingMiddleware
    options:
      show_source: true

## Utilities

### Key Generation

::: aiogram_sentinel.utils.keys.rate_key
    options:
      show_source: true

::: aiogram_sentinel.utils.keys.debounce_key
    options:
      show_source: true

::: aiogram_sentinel.utils.keys.fingerprint
    options:
      show_source: true

::: aiogram_sentinel.utils.keys.user_key
    options:
      show_source: true

### Decorators

::: aiogram_sentinel.decorators.rate_limit
    options:
      show_source: true

::: aiogram_sentinel.decorators.debounce
    options:
      show_source: true

::: aiogram_sentinel.decorators.require_registered
    options:
      show_source: true
