"""Idle-operation rendering commits its component with lifecycle completion."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from aiogram_nav.models import (
    EffectCheckpoint,
    NavigationMutation,
    PreparedAction,
    RenderResult,
    VersionedSnapshot,
)
from aiogram_nav.storage.state import fingerprint

from ...errors import ActivityConflict
from ...models import (
    ActionReceipt,
    ActivitySpec,
    FlowContext,
    Phase,
    RuntimeSnapshot,
    freeze_object,
)
from .codec import COMPONENT, OWNER, load_ledger, save_component
from .engine import reducer

if TYPE_CHECKING:
    from .repository import NavigationRepository


async def stage(
    repo: NavigationRepository,
    context: FlowContext,
    prepared: PreparedAction,
    rendered: RenderResult,
    *,
    operation_id: str,
    disposition: str = "rearm",
) -> ActionReceipt:
    key = repo.mapping.to_nav(context.key)
    current = await repo.idle.backend.load(context.key)
    if (
        current is None
        or current.idle.operation is None
        or current.idle.operation.operation_id != context.operation_id
    ):
        raise ActivityConflict("The idle operation no longer owns staged completion")
    memory = reducer(repo, key, current)
    await memory.checkpoint(
        key,
        operation_id=prepared.operation_id,
        effect=EffectCheckpoint("render", "confirmed", rendered),
    )
    loaded = await memory.load(key)
    result = await memory.commit(
        key,
        expected_version=loaded.version if loaded else None,
        mutation=NavigationMutation(
            prepared.operation_id,
            prepared.session_id,
            rendered,
            accepted_activity=False,
            source="idle",
        ),
    )
    ledger = memory._records[key]
    from .receipts import preserve

    value = preserve(
        save_component(ledger, key, expected_profile=repo.profile),
        current.components.get(COMPONENT),
        ledger,
    )
    retained = max(
        result.snapshot.expires_at / 1000,
        *(entry.retention_until / 1000 for entry in ledger.operations.values()),
    )
    updates = freeze_object(
        {
            COMPONENT: value,
            OWNER: {"component": COMPONENT, "pending": False, "retain_until": retained},
        },
        max_bytes=8_388_608,
    )
    replacement = None
    if disposition == "replacement":
        node = result.snapshot.node_id
        replacement = ActivitySpec(
            repo.policies.activity_for(node),
            repo.policies.policy_for(repo.registry, node),
            repo.adapter_key,
            result.snapshot.params,
            result.snapshot.expires_at / 1000,
        )
    return ActionReceipt(
        operation_id=operation_id,
        disposition=disposition,
        replacement=replacement,
        component_updates=updates,
    )


def finalize(
    repo: NavigationRepository,
    old: RuntimeSnapshot,
    changed: RuntimeSnapshot,
    receipt: ActionReceipt,
) -> RuntimeSnapshot:
    if not receipt.component_updates:
        if (
            COMPONENT in old.components
            and old.activity is not None
            and old.activity.adapter_key == repo.adapter_key
        ):
            raise ActivityConflict("Integrated idle completion requires staged navigation")
        return changed
    if set(receipt.component_updates) != {COMPONENT, OWNER}:
        raise ActivityConflict("Staged navigation cannot update unrelated components")
    if COMPONENT not in old.components:
        raise ActivityConflict("Staged navigation lacks its original ownership slot")
    key = repo.mapping.to_nav(changed.key)
    old_ledger = load_ledger(old, key, expected_profile=repo.profile)
    if old_ledger is None or old_ledger.pending_id != receipt.operation_id:
        raise ActivityConflict(
            "Staged component completion does not own the reserved navigation action"
        )
    ledger = load_ledger(changed, key, expected_profile=repo.profile)
    if ledger is None or ledger.current is None:
        raise ActivityConflict("Staged navigation completion lacks its component")
    original = old_ledger.operations[receipt.operation_id].prepared
    completed = ledger.operations.get(receipt.operation_id)
    if (
        original is None
        or completed is None
        or completed.prepared is None
        or completed.result is None
        or completed.status != "completed"
        or completed.fingerprint != original.fingerprint
        or fingerprint(completed.prepared.intent) != fingerprint(original.intent)
        or any(
            getattr(completed.prepared, name) != getattr(original, name)
            for name in ("key", "session_id", "view_id", "expires_at", "expected_version")
        )
        or completed.result.version != ledger.current.version
        or fingerprint(completed.result.snapshot) != fingerprint(ledger.current.snapshot)
    ):
        raise ActivityConflict("Staged completion changed its reserved navigation identity")
    for name, retained in old_ledger.operations.items():
        if name == receipt.operation_id:
            continue
        updated = ledger.operations.get(name)
        if (updated is None and retained.retention_until > repo.clock.now()) or (
            updated is not None and fingerprint(updated) != fingerprint(retained)
        ):
            raise ActivityConflict("Staged completion changed retained operation evidence")
    if set(ledger.operations) - set(old_ledger.operations):
        raise ActivityConflict("Staged completion introduced unrelated operations")
    nav = ledger.current.snapshot
    activity = changed.activity
    if activity is not None:
        previous = old.activity.activity_revision if old.activity else nav.activity_revision
        accepted = old.idle.phase == Phase.RESUMING
        revision = previous + int(accepted)
        last_activity = activity.last_activity_at if accepted else nav.last_activity_at / 1000
        activity = replace(activity, activity_revision=revision, last_activity_at=last_activity)
        nav = replace(nav, activity_revision=revision, last_activity_at=int(last_activity * 1000))
        if not accepted and changed.idle.deadline is not None:
            policy = repo.idle.policies[activity.policy_id]
            from ...policies import ExemptPolicy

            if not isinstance(policy, ExemptPolicy):
                changed = replace(
                    changed,
                    idle=replace(changed.idle, deadline=last_activity + policy.after_seconds),
                )
        ledger.current = VersionedSnapshot(nav, ledger.current.version)
        for entry in ledger.operations.values():
            if entry.result is not None and entry.result.snapshot.view.view_id == nav.view.view_id:
                entry.result = replace(entry.result, snapshot=nav)
    components = dict(changed.components)
    from .receipts import preserve

    components[COMPONENT] = preserve(
        save_component(ledger, key, expected_profile=repo.profile),
        old.components.get(COMPONENT),
        ledger,
        operation_id=receipt.operation_id,
        activity=activity,
    )
    return replace(
        changed, activity=activity, components=freeze_object(components, max_bytes=8_388_608)
    )
