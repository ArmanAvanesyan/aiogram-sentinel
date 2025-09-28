# Storage API

## Storage Backends

### Memory Backends

::: aiogram_sentinel.storage.MemoryRateLimiter
    options:
      show_source: true

::: aiogram_sentinel.storage.MemoryDebounce
    options:
      show_source: true

::: aiogram_sentinel.storage.MemoryBlocklist
    options:
      show_source: true

::: aiogram_sentinel.storage.MemoryUserRepo
    options:
      show_source: true

### Redis Backends

::: aiogram_sentinel.storage.RedisRateLimiter
    options:
      show_source: true

::: aiogram_sentinel.storage.RedisDebounce
    options:
      show_source: true

::: aiogram_sentinel.storage.RedisBlocklist
    options:
      show_source: true

::: aiogram_sentinel.storage.RedisUserRepo
    options:
      show_source: true

## Storage Protocols

::: aiogram_sentinel.storage.base.RateLimiterBackend
    options:
      show_source: true

::: aiogram_sentinel.storage.base.DebounceBackend
    options:
      show_source: true

::: aiogram_sentinel.storage.base.BlocklistBackend
    options:
      show_source: true

::: aiogram_sentinel.storage.base.UserRepo
    options:
      show_source: true
