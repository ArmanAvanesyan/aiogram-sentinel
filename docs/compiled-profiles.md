# Compiled profiles and optional CPU engines

The default engine is Python. Installing a native module never changes engine
selection. Existing live configurations and translators are evaluated on every
call, preserving dynamic translation behavior.

For repeated menus, explicitly compile a snapshot:

```python
from aiogram_cmds import CommandScopeManager, compile_config

snapshot = compile_config(
    config,
    config_revision="menus-v2",
    translator=translator,
    translation_revision="catalogs-v7",
)
manager = CommandScopeManager(bot, compiled=snapshot)
result = await manager.apply_profile(42, "member", language="ru", language_code=None)
```

Compilation copies configuration and resolves translations immediately. The
snapshot is immutable; returned BotCommand models and configuration objects are
independent copies. Changing application configuration or catalogs does not alter
an existing snapshot. Compile a new snapshot with new revisions when either
changes. Revisions are application-owned labels, not automatic cache keys. A
translator requires an explicit translation revision. Unknown snapshot profiles
or uncompiled locales fail before Telegram operations.

`ProfileRequest` and `build_profile_batch(snapshot, requests)` resolve ordered
menus and fingerprints without network calls. `ResolvedPayload.bot_commands()`
returns fresh SDK objects. Duplicate commands and ordering remain significant.
`manager.build_batch(requests)` additionally checks that each bot identity matches
its manager. Batch application still reports partial success; Telegram has no
transactional multi-menu API. A matching caller-owned confirmed fingerprint skips
sending, and only literal Bot API `True` confirms a new fingerprint.

## Native candidate

The separate `aiogram-cmds-native` companion contains a Rust resolved-profile and
fingerprint CPU core. It has no dependency on this Python package. It is a
candidate, not an advertised dependency extra or published installation promise.
The pure Python wheel needs no Rust compiler, Redis, navigation or native module.

Developers can build the candidate with `uv pip install ./native`, then select
`engine="rust"` on `compile_config`, `CommandScopeManager`,
`build_profile_batch` or `payload_fingerprint`. A manager binds its compiled
snapshot once. Native ABI/version mismatches and missing modules raise
`NativeEngineError` before effects; the library never silently falls back after
an explicit request. Rust receives resolved strings, never translators, async
callbacks, Telegram clients or application business logic. The supported native
ABI is 1 and candidate companion version is 0.3.0.

## Reproducible evidence

Run `python benchmarks/run.py --engine python --output result.json` against an
installed wheel. Use `--engine rust` for an installed companion. The same driver
runs against published 0.2.0 without source-path injection. New compiled APIs are
marked `new_only`, not presented as baseline-comparable features. An orjson
comparator shows how a general serializer compares with the custom engine.

`--quick` is exploratory and cannot qualify publication. Reports include raw CPU
and wall samples, nearest-rank p95, RSS and effect/translation call counts. Realistic
operation p95 uses individual menu calls, separately from batch CPU samples. Fake
network latency is explicitly named and is not a Telegram performance claim.
`benchmarks/pyperf_suite.py` uses pyperf's subprocess runner; native Criterion
benchmarks run with `cargo bench --manifest-path native/Cargo.toml`.

Native publication requires serial matched measurements showing at least 20%
CPU improvement and no greater than 5% realistic p95 regression. No such result is
claimed merely because correctness tests pass. Seven native platform wheels and
Python 3.10–3.14 runtime CI are separate from the pure Python package. Native
release tags use `native-v*`; base tags remain `v*`.
