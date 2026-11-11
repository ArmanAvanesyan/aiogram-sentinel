"""Atomic mapping of accepted navigation and idle lifecycle state."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from aiogram_nav.models import ConversationKey
from aiogram_nav.storage.state import Conversation

from ...errors import ActivityConflict
from ...models import (
    ActivitySnapshot,
    IdleSnapshot,
    Phase,
    RuntimeSnapshot,
    SessionSnapshot,
    freeze_object,
)
from ...policies import ExemptPolicy, IdlePolicy
from ...storage.codec import decode, encode
from ...storage.session_bindings import EXTERNAL_SESSION
from .codec import COMPONENT, OWNER
from .engine import STAGING

if TYPE_CHECKING:
    from .repository import NavigationRepository


def compose(
    repo: NavigationRepository,
    key: ConversationKey,
    current: RuntimeSnapshot | None,
    ledger: Conversation,
    value: Mapping[str, object],
    *,
    accepted: bool,
    enabled: bool,
    restart: bool = False,
    operation_id: str | None = None,
    reply_overlay: bool = False,
    canonical: bool = False,
) -> tuple[RuntimeSnapshot, IdlePolicy | None]:
    now = repo.idle.clock.now()
    prepared = ledger.operations[ledger.pending_id].prepared if ledger.pending_id else None
    snapshot = ledger.current.snapshot if ledger.current else None
    session_id = prepared.session_id if prepared else snapshot.session_id if snapshot else None
    expiry = prepared.expires_at if prepared else snapshot.expires_at if snapshot else None
    if session_id is None and expiry is None and current is not None:
        # Abandoning the first prepared view leaves no current/pending Nav view.
        # The already committed Idle session remains authoritative, including expiry.
        session_id = current.session.session_id
        expiry = round(current.session.expires_at * 1000)
    if session_id is None or expiry is None:
        raise ActivityConflict("Navigation component lacks a session generation")
    if current is None:
        current = RuntimeSnapshot(
            repo.mapping.to_idle(key), SessionSnapshot(session_id, expiry / 1000)
        )
    elif current.session.session_id != session_id:
        external = ledger.external_session
        old_binding = current.components.get(EXTERNAL_SESSION)
        external_rotation = (
            external is not None
            and isinstance(old_binding, Mapping)
            and old_binding.get("session_id") != external.session_id
        )
        if (
            current.session.expires_at > now and not external_rotation
        ) or current.idle.operation is not None:
            raise ActivityConflict("Cannot replace the authoritative live session")
        current = RuntimeSnapshot(
            current.key, SessionSnapshot(session_id, expiry / 1000), components=current.components
        )
    elif COMPONENT not in current.components and current.activity is not None:
        raise ActivityConflict("A standalone activity cannot be adopted implicitly")
    components: dict[str, object] = dict(current.components)
    if ledger.external_session is not None:
        external = ledger.external_session
        components[EXTERNAL_SESSION] = {
            "session_id": external.session_id,
            "revision": external.revision,
            "absolute_expires_at": external.absolute_expires_at,
        }
    previous_component = components.get(COMPONENT)
    body = dict(value)
    body["reply_overlay"] = reply_overlay
    idle = current.idle
    policy = None
    activity = current.activity
    if accepted and snapshot is not None:
        activity_key = repo.policies.activity_for(snapshot.node_id)
        policy_id = repo.policies.policy_for(repo.registry, snapshot.node_id)
        policy = repo.idle.policies[policy_id]
        same = (
            activity
            if not restart
            and activity is not None
            and activity.activity_key == activity_key
            and activity.expires_at > now
            else None
        )
        activity = ActivitySnapshot(
            session_id,
            same.activity_id if same else secrets.token_urlsafe(18),
            activity_key,
            snapshot.activity_revision,
            policy_id,
            repo.adapter_key,
            snapshot.params,
            same.entered_at if same else snapshot.entered_at / 1000,
            snapshot.last_activity_at / 1000,
            snapshot.expires_at / 1000,
        )
        idle = (
            IdleSnapshot()
            if isinstance(policy, ExemptPolicy) or not enabled
            else IdleSnapshot(
                phase=Phase.ACTIVE, deadline=activity.last_activity_at + policy.after_seconds
            )
        )
    if prepared is not None:
        if accepted:
            body["suspended_idle"] = encode(replace(idle, operation=None) if canonical else idle)
        elif isinstance(previous_component, Mapping) and "suspended_idle" in previous_component:
            body["suspended_idle"] = previous_component["suspended_idle"]
        else:
            body["suspended_idle"] = encode(
                replace(current.idle, operation=None) if canonical else current.idle
            )
        if STAGING.get() is None:
            idle = replace(idle, deadline=now + repo.idle.config.poll_seconds)
    elif (
        not accepted
        and isinstance(previous_component, Mapping)
        and "suspended_idle" in previous_component
    ):
        restored = decode(str(cast(Mapping[str, object], previous_component)["suspended_idle"]))
        if not isinstance(restored, IdleSnapshot):
            raise ActivityConflict("Malformed suspended idle lifecycle")
        idle = restored
    retained = max(
        [expiry / 1000, *(entry.retention_until / 1000 for entry in ledger.operations.values())]
    )
    from .receipts import preserve

    if canonical:
        components[COMPONENT] = freeze_object(body, max_bytes=8_388_608)
    else:
        components[COMPONENT] = preserve(
            freeze_object(body, max_bytes=8_388_608),
            cast(object, previous_component),
            ledger,
            operation_id=operation_id if accepted else None,
            activity=activity if accepted else None,
        )
    components[OWNER] = {
        "component": COMPONENT,
        "pending": prepared is not None,
        "retain_until": retained,
        "recovery_at": now + repo.idle.config.poll_seconds,
    }
    return replace(
        current,
        activity=activity,
        idle=idle,
        recovery_until=max(current.recovery_until, retained),
        components=freeze_object(components, max_bytes=8_388_608),
    ), policy
