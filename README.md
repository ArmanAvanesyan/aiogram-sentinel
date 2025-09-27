# aiogram-sentinel

Edge hygiene library for aiogram v3.

## Features

- **Middlewares**: Blocking, Auth, Debouncing, Throttling
- **Router**: my_chat_member sync with on_block/on_unblock hooks  
- **Backends**: memory & redis via SentinelConfig
- **Setup helper**: Sentinel.setup(dp, cfg, router=None)
- **Decorators**: @rate_limit, @debounce, @require_registered

## Installation

```bash
pip install aiogram-sentinel
```

## Quick Start

```python
from aiogram import Dispatcher
from aiogram_sentinel import Sentinel, SentinelConfig

# Configure
config = SentinelConfig(
    redis_url="redis://localhost:6379",
    redis_prefix="my_bot:"
)

# Setup
dp = Dispatcher()
Sentinel.setup(dp, config)
```

## License

MIT License - see [LICENSE](LICENSE) file for details.
