# aiogram-nav

Standalone navigation for aiogram 3. The current local slice supplies core
contracts, memory and optional Redis repositories, prepared rendering, input bindings and FSM
coexistence. See [quickstart](quickstart.md) and [verification](verification.md).

Navigation does not depend on aiogram-idle. The
[optional combined adapter](idle-integration.md) lives in aiogram-idle and must be
selected explicitly.
[Redis storage](redis.md) is available through the `redis` extra.

Start with the quickstart, then review [storage and recovery](storage.md),
[security boundaries](security.md) and the public API. Maintainers can follow the
[release procedure](releasing.md); it does not run automatically on a push.
