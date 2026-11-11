# Navigation concepts

A node describes a screen, independent of how somebody reached it. A command,
reply label, inline token or application handler can enter the same node. Stable
IDs are opaque strings; dotted names do not imply a relationship. The registered
parent tree defines grouping and inherited targets explicitly.

An abstract node has no renderer and cannot be entered directly. Roots and action
targets must exist, parent relationships must be acyclic, and every concrete node
must be reachable from a root. Multiple roots support distinct application
contexts. Cross-root movement needs an explicit destination and authorization.

## Location, activity and storage

Navigation snapshots store the committed node, validated reconstruction parameters,
a random session ID, the current view and optional bounded history. Navigation
revision changes with location, parameters or view identity. Activity revision
changes only for accepted activity. Storage CAS versions are a separate token:
an effect checkpoint can advance storage state without claiming another screen
was displayed or another user action occurred.

Times are integer epoch milliseconds internally. Session expiry is absolute;
refreshing or accepting input does not silently extend its authorization lifetime.
An expired/recreated session receives a new random ID so historical inline controls
cannot mutate it.

The memory repository coordinates callers in one process. It does not share state
between replicas and cannot recover anything after process restart. See
[storage and recovery](storage.md) for the prepare/effect/commit lifecycle.

## Back, Home and Cancel

Back prefers the node's explicit `back_to`, then valid bounded history, then the
configured root. Back at the root refreshes it without growing history. Home uses
an explicit/configured root. Cancel follows the nearest inherited `cancel_to`.
None of these actions guess a parent by splitting a node ID.

Navigation does not own application drafts. Back does not clear FSM data. Cancel
can invoke an explicitly supplied application hook, with a stable operation ID,
before rendering its destination. That hook must limit changes to the draft it
owns and fence or deduplicate durable business writes.

## Input and authorization

Buttons express an entry route, not permission. Every route executes the same
validation and authorization pipeline. Reply text equal to a button label cannot
be distinguished from typing the label manually; commands and reply labels act on
the currently authorized navigation state. They do not carry historical-view
provenance.

Inline callbacks carry opaque server-side tokens bound to actor, conversation,
session and view. Tokens for a prepared view cannot act before that view commits.
Old/stale callbacks are acknowledged and cleaned up best-effort.

Free-form input nodes can set `metadata={"reply_navigation": False}` to suppress
scoped reply navigation. Explicit global reply actions remain available, so a
consumer can offer Back or Cancel during typing without interpreting unrelated
text as navigation.
