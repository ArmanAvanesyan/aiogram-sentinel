"""Reference-only idle receipts and one atomic canonical navigation completion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from aiogram_nav.models import EffectCheckpoint, NavigationMutation, PreparedAction, RenderResult

from ...errors import ActivityConflict, EffectUnknown, OwnershipLost
from ...models import ActionReceipt, ActivitySpec, FlowContext, RuntimeSnapshot, freeze_object
from ...policies import IdlePolicy
from ...storage.state import Claim
from .canonical import CanonicalHost, read, save_activity, value
from .codec import COMPONENT, OWNER, load_ledger, save_component

if TYPE_CHECKING:
    from .repository import NavigationRepository


async def stage(
    repo: NavigationRepository,
    context: FlowContext,
    prepared: PreparedAction,
    rendered: RenderResult,
    *,
    operation_id: str,
    disposition: str,
) -> ActionReceipt:
    key = repo.mapping.to_nav(context.key)
    current = await repo.idle.backend.load(context.key)
    if (
        current is None
        or current.idle.operation is None
        or current.idle.operation.operation_id != context.operation_id
    ):
        raise OwnershipLost("The idle operation no longer owns canonical rendering")
    if operation_id != prepared.operation_id:
        raise ActivityConflict("Canonical stage operation identity changed")
    await repo.checkpoint(
        key,
        operation_id=operation_id,
        effect=EffectCheckpoint("render", "confirmed", rendered),
        coordination_scope=repo.coordinator.scope_token(key),
    )
    replacement = None
    if disposition == "replacement":
        node = prepared.intent.node_id
        replacement = ActivitySpec(
            repo.policies.activity_for(node),
            repo.policies.policy_for(repo.registry, node),
            repo.adapter_key,
            prepared.intent.params,
            prepared.expires_at / 1000,
        )
    return ActionReceipt(
        operation_id,
        disposition=disposition,
        replacement=replacement,
        component_updates=freeze_object({COMPONENT: {"canonical_stage": operation_id}}),
    )


async def complete(
    repo: NavigationRepository,
    old: RuntimeSnapshot,
    changed: RuntimeSnapshot,
    receipt: ActionReceipt,
    policy: object,
    claim: object,
) -> RuntimeSnapshot | None:
    original = old.components.get(COMPONENT)
    if not isinstance(original, Mapping) or original.get("schema") != 3:
        return None
    reference = receipt.component_updates.get(COMPONENT)
    if (
        set(receipt.component_updates) != {COMPONENT}
        or not isinstance(reference, Mapping)
        or set(reference) != {"canonical_stage"}
        or reference["canonical_stage"] != receipt.operation_id
    ):
        raise ActivityConflict("Canonical idle completion requires its staged operation reference")
    if old.idle.operation is None:
        raise OwnershipLost("Idle completion no longer owns the operation")
    key = repo.mapping.to_nav(old.key)
    await repo.authorize_session(key, old.session.session_id)
    reducer = await read(repo, key, operation_id=receipt.operation_id)
    ledger = reducer.record
    if ledger is None or ledger.pending_id != receipt.operation_id:
        raise ActivityConflict("Canonical completion does not own the pending navigation")
    prepared = ledger.operations[receipt.operation_id].prepared
    effect = prepared.effects.get("render") if prepared else None
    if (
        prepared is None
        or effect is None
        or effect.state != "confirmed"
        or not isinstance(effect.result, RenderResult)
    ):
        raise EffectUnknown("Canonical rendering has no confirmed result")
    # Existing audited normalization operates on bounded transient projections.
    # Neither view is persisted as an Idle acknowledgement or staging snapshot.
    before = save_component(ledger, key, expected_profile=repo.profile)
    unloaded = ledger.unloaded_operations
    current = await reducer.repository.load(key)
    result = await reducer.repository.commit(
        key,
        expected_version=current.version if current else None,
        mutation=NavigationMutation(
            receipt.operation_id,
            prepared.session_id,
            effect.result,
            accepted_activity=False,
            source="idle",
        ),
    )
    committed_ledger = reducer.record
    if committed_ledger is None:
        raise OwnershipLost("Canonical navigation completion lost its operation ledger")
    after = save_component(committed_ledger, key, expected_profile=repo.profile)
    retained = max(
        result.snapshot.expires_at / 1000,
        *(entry.retention_until / 1000 for entry in committed_ledger.operations.values()),
    )
    owner = {"component": COMPONENT, "pending": False, "retain_until": retained}
    updates = freeze_object({COMPONENT: after, OWNER: owner}, max_bytes=8_388_608)
    temporary_old = replace(old, components={**old.components, COMPONENT: before})
    temporary_changed = replace(changed, components={**changed.components, **updates})
    from .staging import finalize

    normalized = finalize(
        repo, temporary_old, temporary_changed, replace(receipt, component_updates=updates)
    )
    normalized_ledger = load_ledger(normalized, key, expected_profile=repo.profile)
    if normalized_ledger is None:
        raise ActivityConflict("Canonical normalization lost its navigation state")
    normalized_ledger.unloaded_operations = unloaded
    reducer.replace_record(normalized_ledger)
    if normalized.activity is not None:
        save_activity(reducer, receipt.operation_id, normalized.activity)
    desired = replace(
        normalized, components={**normalized.components, COMPONENT: value(repo, key, reducer)}
    )
    manifest = await repo.idle.manifest()
    return await cast(CanonicalHost, repo.idle.backend).canonical_component_transaction(
        old.key,
        component=COMPONENT,
        expected_version=old.store_version,
        record=desired,
        ledger_delta=reducer.delta().to_payload(),
        policy=cast(IdlePolicy | None, policy),
        coordination_scope=repo.coordinator.scope_token(key),
        expected_manifest=manifest.generation,
        allow_idle_operation_id=old.idle.operation.operation_id,
        finalize_idle_operation_id=old.idle.operation.operation_id,
        claim=cast(Claim | None, claim),
    )
