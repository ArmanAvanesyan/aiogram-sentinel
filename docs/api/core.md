# Core API

## Main Classes

::: aiogram_sentinel.Sentinel
    options:
      show_source: true
      members:
        - setup
        - add_hooks

::: aiogram_sentinel.SentinelConfig
    options:
      show_source: true
      members:
        - __init__
        - throttling_default_max
        - throttling_default_per_seconds
        - debounce_default_window
        - backend
        - redis_url
        - redis_prefix

## Middleware

::: aiogram_sentinel.middlewares.ThrottlingMiddleware
    options:
      show_source: true

::: aiogram_sentinel.middlewares.DebounceMiddleware
    options:
      show_source: true

## Decorators

::: aiogram_sentinel.decorators.rate_limit
    options:
      show_source: true

::: aiogram_sentinel.decorators.debounce
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



