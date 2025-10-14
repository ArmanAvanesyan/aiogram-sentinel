# Core API

## Policy Registry

::: aiogram_sentinel.PolicyRegistry
    options:
      show_source: true
      members:
        - register
        - get
        - all
        - clear

::: aiogram_sentinel.Policy
    options:
      show_source: true
      members:
        - name
        - kind
        - cfg
        - description

::: aiogram_sentinel.ThrottleCfg
    options:
      show_source: true
      members:
        - rate
        - per
        - scope
        - method
        - bucket

::: aiogram_sentinel.DebounceCfg
    options:
      show_source: true
      members:
        - window
        - scope
        - method
        - bucket

::: aiogram_sentinel.policy
    options:
      show_source: true

::: aiogram_sentinel.coerce_scope
    options:
      show_source: true

::: aiogram_sentinel.resolve_scope
    options:
      show_source: true

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

::: aiogram_sentinel.InfraBundle
    options:
      show_source: true
      members:
        - throttling_backend
        - debounce_backend

::: aiogram_sentinel.RateLimiterBackend
    options:
      show_source: true
      members:
        - allow
        - cleanup_expired

::: aiogram_sentinel.KeyBuilder
    options:
      show_source: true
      members:
        - __init__
        - for_update
        - user
        - chat
        - group
        - global_

::: aiogram_sentinel.KeyParts
    options:
      show_source: true
      members:
        - namespace
        - scope
        - identifiers

::: aiogram_sentinel.Scope
    options:
      show_source: true
      members:
        - USER
        - CHAT
        - GROUP
        - GLOBAL

## Context Extractors

::: aiogram_sentinel.context.extract_user_id
    options:
      show_source: true

::: aiogram_sentinel.context.extract_chat_id
    options:
      show_source: true

::: aiogram_sentinel.context.extract_group_ids
    options:
      show_source: true

::: aiogram_sentinel.context.extract_event_type
    options:
      show_source: true

::: aiogram_sentinel.context.extract_handler_bucket
    options:
      show_source: true

::: aiogram_sentinel.context.extract_callback_bucket
    options:
      show_source: true

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

::: aiogram_sentinel.decorators.policy
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



