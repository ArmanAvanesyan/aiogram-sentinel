# Integrating existing handlers

Adopt stable node IDs and explicit reconstruction parameters first. Register the
existing screen functions behind presenter renderer keys, or keep the functions
and use the tracking APIs. Application FSM state and draft data remain yours.

## Dispatcher order

Configure FSM storage and event isolation before installing navigation. Install
navigation's context middleware and binding router before including business
routers. Put application message/callback handlers on their own `Router`, included
after navigation. A Dispatcher's own root handlers run ahead of every child
router, so automatic bindings reject that ambiguous arrangement. Without automatic
bindings, existing handlers can use the injected context explicitly.

Disabled FSM event isolation is not treated as a held lock: the navigation
coordinator covers the whole protected handler. A verified `SimpleEventIsolation`
instance can be shared and borrowed without recursive acquisition. Unsupported
strategies or lock configurations fail configuration checks. Do not replace FSM
middleware or isolation after installation.

## Already-rendered screens

Use `track(node_id, params=..., rendered=receipt)` after an existing helper confirms
its delivery. This commits the screen without sending it again. It is a migration
convenience and cannot reconstruct a send lost before tracking began.

For recovery across interrupted rendering within the live memory process, call
`prepare_render(node_id, operation_id=...)` first, send through the stage recorder,
and call `complete_render(prepared, rendered=receipt)`. Preserve stable action and
stage IDs when retrying. Do not hide an uncertain send by choosing a new action ID
and automatically invoking the same helper again.

## Business drafts

Keep accepted text in application storage, then call `touch()` when acceptance
succeeds. Rejected input should not move navigation or refresh activity. Back and
Home do not clear FSM drafts. Add an explicit idempotent cancellation hook if
Cancel should discard a draft; clear only the state and keys that flow owns.

Changing node names requires an explicit registry migration mapping or an explicit
safe-root recovery. Dotted IDs are opaque; the library does not guess a replacement
node by removing suffixes.

There is no automatically enabled aiogram-idle integration. Preserve separate
storage ownership until a tested atomic projection adapter is selected explicitly.

## Upgrade 0.1 to 0.2 in two stages

1. Back up Redis and deploy 0.2 while retaining owned sessions and default storage
   format 1. Coordination uses the same canonical lock keys; ordinary writes remain
   format 1 during this rollout.
2. Stop old worker admission, drain every 0.1 process and active protected handler,
   then run a read-only namespace assessment with the matching configuration:

   ```sh
   AIOGRAM_NAV_REDIS_URL=redis://localhost:6379/0 \
     uv run --no-sync python tools/migrate_storage.py --prefix aiogram-nav
   ```

3. Explicitly apply activation with a stable operation ID and the drained assertion:

   ```sh
   AIOGRAM_NAV_REDIS_URL=redis://localhost:6379/0 \
     uv run --no-sync python tools/migrate_storage.py --prefix aiogram-nav \
       --apply --old-workers-drained --operation-id reviewed-upgrade-020
   ```

4. Enable external session authority only after activation. The activation manifest
   changes the profile/history atomically, fencing old cached writers and old startup
   code. New readers accept existing format-1 records and lazily write format 2.
   No presenter or business action runs during assessment or activation.

For custom storage settings or restricted Redis introspection, call the public
repository activation API with the application's exact configuration and attestation
instead of the default CLI. The CLI never prints credentials; prefer the environment
variable over URL command arguments. The migration retains current views, tokens,
receipts and unresolved effects. Retry the same applied operation ID after a lost
response; a different mutation intent is rejected.

Before activation, binary rollback remains possible. After activation, old writers
must not rejoin the namespace: use a compatible forward fix or coordinated backup
restoration, never a simple binary downgrade. Memory repositories also require
explicit activation for external sessions; their state is non-durable.

See [application-owned integration](application-integration.md) for the public
custom-isolation wrapper, application cleanup and manual routing recipes.
