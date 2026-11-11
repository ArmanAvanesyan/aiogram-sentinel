# Migrating to 0.2

Version 0.2 includes the generic profile API, corrected aiogram locale/plural
adapter, matching runtime/distribution versions, scope validation and observable
manager errors. The base package still installs neither Redis nor a navigation
or idle framework. Command menus do not authorize or implement handlers.

## Render language and Telegram menu slot

`language` controls how descriptions are rendered. `language_code` controls where
Telegram stores the list. Omitting `language_code` preserves historical behavior:
it uses `language`, unless the supplied configuration explicitly sets
`per_language=False`. An explicit string overrides that configuration. Explicit `None` (or an empty string) omits that Bot API field
and targets the default-language slot.

```python
from aiogram_cmds import CommandScopeManager

manager = CommandScopeManager(bot, config=config, translator=translator)
# Render Russian descriptions, but install one default-language list.
await manager.update_profile(42, "member", language="ru", language_code=None)
```

A default-language list is a fallback. Existing language-specific lists can still
override it. Remove only the obsolete slots that the application owns:

```python
await manager.clear_language_variants(42, ["en", "ru", "hy"])
```

This never deletes the default slot and never discovers or guesses languages.
Deletion, like configuration, is not atomic: earlier confirmed requests remain
applied if a later request fails. Invalid containers or empty codes are rejected
before any request is sent. For group member menus, pass the same `chat_id` used
when installing those menus.

For configuration-wide behavior use `CmdsConfig(per_language=False, ...)`.
Each scope inherits that setting unless `ScopeDef(per_language=...)` overrides it.
Single-list configuration renders the first scope language, otherwise the first
global language, otherwise English. It sends exactly one list per scope without
`language_code`; setting it does not delete old language-specific menus.

## Explicit outcomes and caller-owned confirmations

Existing manager methods keep Boolean results:

| Method family | Success | Error by default | `best_effort=True` |
| --- | --- | --- | --- |
| `update_profile`, legacy updates, clearing, `setup_all` | `True` | original exception | `False` |
| `apply_profile` | `applied` or `unchanged` result | original exception | `failed` result |
| `apply_all` | `applied` batch result | original exception | `partial` or `failed` batch result |

Low-level `set_user_profile`, `apply_config` and `clear_language_variants` retain
`None` on success and propagate errors. `apply_config_result` provides explicit
batch outcomes. Invalid programmer arguments (such as a malformed confirmation
hash) are rejected before effects, including in best-effort mode.

Cancellation always propagates. A successful request is not a Telegram
transaction: earlier changes cannot be rolled back by a later failure. Batch
results record confirmed targets, the failed target and original error; the menu
button is a separate target. Scope validation and rendering happen before the
first batch request.

```python
result = await manager.apply_profile(
    42, "member", language="en", language_code=None,
    previous_fingerprint=application_cache.get(cache_key),
)
if result.confirmed_fingerprint is not None:
    application_cache[cache_key] = result.confirmed_fingerprint
```

The library owns no cache. Fingerprints include bot identity, full scope,
normalized Telegram language slot and the ordered rendered command/description
payload. An identical caller-confirmed fingerprint yields `unchanged` without a
Bot API call. Only `confirmed_fingerprint` may be stored as a successful
confirmation. Failures, non-`True` Bot API responses and ambiguous timeouts never
confirm it. A lost response may mean Telegram applied the list; safely retry the
same setter without inventing a confirmation.

Invalidate application confirmations if another process, an administrator or
another integration changes the menu. A local hash is not a distributed lock,
exactly-once guarantee, or a query of Telegram's current state. Serialize competing
writers in the application when that is required.

## Application-selected profiles

Prefer `update_profile`/`apply_profile` with application-selected profile names.
The registration/vehicle flag API remains a compatibility layer. Generic profiles
can describe any application domain. The new `apply_profile` rejects an unknown
profile before effects; legacy registry behavior is retained by older wrappers.

See the runnable `examples/application_profiles.py` example in the repository.
`--dry-run` exercises apply/unchanged behavior without contacting Telegram.
