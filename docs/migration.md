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
