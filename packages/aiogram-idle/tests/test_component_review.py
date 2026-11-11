"""Component ownership cannot overwrite the idle worker's transaction ledger."""

from dataclasses import replace

import pytest

from aiogram_idle.errors import ActivityConflict
from aiogram_idle.models import IdleSnapshot, PendingOperation, Phase
from tests.test_component_transactions import KEY, commit, first
from tests.test_component_transactions import backend as _backend

backend = _backend


async def test_existing_component_cannot_create_an_unrelated_slot(backend):
    current = await commit(backend, first(backend))
    changed = replace(current, components={**current.components, "new-foreign-slot": {"value": 1}})
    with pytest.raises(ActivityConflict, match="unrelated"):
        await commit(backend, changed, version=current.version, operation="foreign-insert")
    assert await backend.load(KEY) == current


@pytest.mark.parametrize("change", ["remove-operation", "alter-effect", "replace-activity"])
async def test_staged_component_preserves_reserved_idle_ledger_and_activity(backend, change):
    current = await commit(backend, first(backend))
    operation = PendingOperation(
        "idle-op", "continue", started_at=backend.clock.now(), effects={"business": "started"}
    )
    current = await backend.transition(
        KEY,
        expected_version=current.version,
        operation_id="reserve-op",
        fingerprint="reserve-op",
        transform=lambda old: replace(
            old, idle=IdleSnapshot(phase=Phase.RESUMING, operation=operation)
        ),
    )
    if change == "remove-operation":
        changed = replace(current, idle=IdleSnapshot())
    elif change == "alter-effect":
        changed = replace(
            current,
            idle=replace(
                current.idle, operation=replace(operation, effects={"business": "confirmed"})
            ),
        )
    else:
        changed = replace(current, activity=replace(current.activity, params={"draft": "changed"}))
    async with backend.coordinator.hold(KEY):
        with pytest.raises(ActivityConflict, match="idle operation or activity"):
            await backend.component_transaction(
                KEY,
                component="opaque",
                expected_version=current.version,
                operation_id=f"stage-{change}",
                fingerprint=f"stage-{change}",
                record=changed,
                allow_idle_operation_id="idle-op",
                coordination_scope=backend.coordinator.scope_token(KEY),
            )
    assert await backend.load(KEY) == current
