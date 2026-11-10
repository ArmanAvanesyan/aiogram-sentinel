# aiogram-idle

Add inactivity questions or quiet cleanup to aiogram 3 handlers and FSM flows.
Applications explicitly accept activity and provide business adapters. A navigation
framework is optional.

The base package provides single-process memory storage. The `redis` extra adds
shared storage and coordination; `nav` adds the separate aiogram-nav integration.
All four prompt styles—reply, inline, commands and hybrid—work independently of
navigation. Prompt creation is disabled by default.

Start with [installation](installation.md) and the [quickstart](quickstart.md),
then read [standalone integration](standalone.md) and [recovery](recovery.md).
[Public API](api.md) lists the contract groups; [architecture](architecture.md)
explains state and effect ownership. Use [Redis](redis.md) for multiple processes,
or [optional navigation](navigation.md) to coordinate navigation and idle activity.

The `0.1.0` distribution is not published to PyPI. Source installation is supported;
the [release process](releasing.md) is a separate maintainer action. See
[testing and compatibility](testing.md) for current checks and
[verification](verification.md) for dated implementation evidence.
