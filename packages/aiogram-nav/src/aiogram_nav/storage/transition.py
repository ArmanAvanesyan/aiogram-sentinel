"""Pure state/history transition boundary shared by deterministic engines."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

from ..codec import decode_value, encode_value
from ..config import NavigationConfig
from ..engine import native_core
from ..models import HistoryEntry, NavigationMutation, NavigationSnapshot, PreparedAction


def transition(
    old: NavigationSnapshot | None,
    prepared: PreparedAction,
    mutation: NavigationMutation,
    *,
    config: NavigationConfig,
    now: int,
    fingerprint: Callable[[object], str],
) -> tuple[tuple[HistoryEntry, ...], dict[str, int]]:
    params_changed = old is None or fingerprint(old.params) != fingerprint(prepared.params)
    accepted = prepared.intent.accepted_activity and mutation.accepted_activity
    limit = config.history_limit
    mode = prepared.intent.history
    if config.engine == "python":
        history = old.history if old else ()
        if (
            mode == "push"
            and old is not None
            and (old.node_id != prepared.node_id or params_changed)
        ):
            history = (*history, HistoryEntry(old.node_id, old.params))
        elif mode == "pop":
            amount = getattr(prepared.intent, "history_pop", 1)
            history = history[:-amount] if amount else history
        elif mode == "clear":
            history = ()
        history = history[-limit:] if limit else ()
        state = dict(
            nav_revision=(old.nav_revision + 1) if old else 1,
            activity_revision=(old.activity_revision + int(accepted)) if old else 1,
            entered_at=now
            if old is None or old.node_id != prepared.node_id or params_changed
            else old.entered_at,
            last_activity_at=now if accepted or old is None else old.last_activity_at,
        )
        return history, state
    else:
        core = native_core()
        previous = (
            None
            if old is None
            else json.dumps(
                dict(
                    node_id=old.node_id,
                    nav_revision=old.nav_revision,
                    activity_revision=old.activity_revision,
                    entered_at=old.entered_at,
                    last_activity_at=old.last_activity_at,
                )
            )
        )
        state = json.loads(
            core.transition_state(previous, prepared.node_id, params_changed, accepted, str(now))
        )
        previous_history = old.history if old else ()
        current_entry = encode_value(HistoryEntry(old.node_id, old.params)) if old else None
        raw_history = core.transition_history(
            json.dumps([encode_value(item) for item in previous_history]),
            json.dumps(current_entry) if current_entry is not None else None,
            mode,
            limit,
            getattr(prepared.intent, "history_pop", 1),
            old is not None and (old.node_id != prepared.node_id or params_changed),
        )
        history = tuple(cast(HistoryEntry, decode_value(item)) for item in json.loads(raw_history))
    return history, state
