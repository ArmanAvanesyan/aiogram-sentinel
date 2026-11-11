"""Interrupted optional navigation stages retain their own recovery semantics."""

from dataclasses import replace

import pytest

pytest.importorskip("aiogram_nav")

from aiogram_idle.effects import OperationEffects
from aiogram_idle.models import FlowContext, IdleSnapshot, PendingOperation, Phase
from tests.test_nav_atomic_recovery import KEY, build
from tests.test_nav_matrix import combined_backend as _combined_backend

combined_backend = _combined_backend


async def test_staged_prepare_can_recover_lost_outer_receipt(combined_backend):
    backend = combined_backend
    idle, integration, nav, presenter = build(backend)
    await nav.for_conversation(KEY).go("editor", params={"draft_id": "draft"}, operation_id="entry")
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    async with idle.coordinator.hold(mapped):
        record = await backend.load(mapped)
        record = await backend.transition(
            mapped,
            expected_version=record.version,
            operation_id="reserve-answer",
            fingerprint="reserve-answer",
            transform=lambda old: replace(
                old,
                idle=IdleSnapshot(
                    phase=Phase.RESUMING,
                    deadline=backend.clock.now(),
                    operation=PendingOperation(
                        "answer", "continue", started_at=backend.clock.now()
                    ),
                ),
            ),
        )
        effects = OperationEffects(idle, mapped, "answer", None)
        context = FlowContext(
            mapped, record.activity, "answer", backend.clock.now(), effects=effects
        )
        repo = integration.navigation_repository
        async with repo.staging(context):
            reserved = await repo.prepare_staged(context, "editor", operation_id="answer")
        if backend.active_storage_format == 3:
            # Canonical prepare persists the reservation; the render effect is
            # started only immediately before the presenter is invoked.
            assert reserved.effects.get("render") is None
            assert (await repo.pending(KEY)).operation_id == "answer"
        else:
            assert reserved.effects["render"].state == "started"
        before = presenter.calls
        # The process can die here, before nav:prepare's outer receipt exists.
        receipt = await idle.adapters["aiogram_nav"].resume(context, operation_id="answer")
        assert receipt.component_updates and presenter.calls == before + 1
        assert (await repo.pending(KEY)).operation_id == "answer"


async def test_corrupt_cached_view_is_rejected_before_presenter_effect(combined_backend):
    from aiogram_nav.codec import encode

    from aiogram_idle.errors import EffectUnknown

    backend = combined_backend
    idle, integration, nav, presenter = build(backend)
    await nav.for_conversation(KEY).go("editor", params={"draft_id": "draft"}, operation_id="entry")
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    async with idle.coordinator.hold(mapped):
        record = await backend.load(mapped)
        record = await backend.transition(
            mapped,
            expected_version=record.version,
            operation_id="reserve-corrupt",
            fingerprint="reserve-corrupt",
            transform=lambda old: replace(
                old,
                idle=IdleSnapshot(
                    phase=Phase.RESUMING,
                    deadline=backend.clock.now(),
                    operation=PendingOperation(
                        "answer", "continue", started_at=backend.clock.now()
                    ),
                ),
            ),
        )
        effects = OperationEffects(idle, mapped, "answer", None)
        context = FlowContext(
            mapped, record.activity, "answer", backend.clock.now(), effects=effects
        )
        repo = integration.navigation_repository
        async with repo.staging(context):
            prepared = await repo.prepare_staged(context, "editor", operation_id="answer")
        await effects.checkpoint("nav:prepare", "started")
        await effects.checkpoint(
            "nav:prepare", "confirmed", encode(replace(prepared, view_id="unowned-view"))
        )
        before = presenter.calls
        with pytest.raises(EffectUnknown, match="Cached navigation reservation"):
            await idle.adapters["aiogram_nav"].resume(context, operation_id="answer")
        assert presenter.calls == before
        assert (await repo.pending(KEY)).view_id == prepared.view_id


async def test_restore_cannot_reuse_preparation_for_rejected_resume(combined_backend):
    from aiogram.exceptions import TelegramRetryAfter
    from aiogram.methods import SendMessage

    from aiogram_idle.controls import ControlContext
    from aiogram_idle.models import FlowEligibility
    from tests.runtime_helpers import Adapter

    backend = combined_backend
    idle, integration, nav, presenter = build(backend)
    business = Adapter()
    integration.adapters["editor"] = business
    await nav.for_conversation(KEY).go("editor", params={"draft_id": "draft"}, operation_id="entry")
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    before = await backend.load(mapped)
    await backend.transition(
        mapped,
        expected_version=before.version,
        operation_id="question-due",
        fingerprint="question-due",
        transform=lambda old: replace(old, idle=replace(old.idle, deadline=backend.clock.now())),
    )
    await idle.run_once()
    original = presenter.render
    attempts = []

    async def rejected(request):
        attempts.append(request.node_id)
        raise TelegramRetryAfter(
            method=SendMessage(chat_id=42, text="screen"), message="retry later", retry_after=1
        )

    presenter.render = rejected
    assert (await idle.continue_current(ControlContext(mapped, 42, operation_id="answer"))).accepted
    assert attempts == ["editor"]
    record = await backend.load(mapped)
    assert record.idle.phase is Phase.RESUMING
    business.eligibility = FlowEligibility(resumable=False)
    presenter.render = original
    calls = presenter.calls
    async with idle.coordinator.hold(mapped):
        await idle.worker.execute(record, None)
    retained = await backend.load(mapped)
    # Cancellation cannot call a renderer with the previous resume destination.
    assert presenter.calls == calls
    assert (await nav.for_conversation(KEY).current()).node_id == "editor"
    assert retained.idle.operation is not None
    assert retained.idle.operation.failure_reason == "EffectUnknown"
    assert business.calls.count("abandon:expired") == 1


@pytest.mark.parametrize("corruption", ["target", "retained_receipt", "current_params"])
async def test_finalization_rejects_staged_ledger_unrelated_to_reservation(
    combined_backend, corruption
):
    from aiogram_nav.storage.redis_codec import dumps, loads
    from aiogram_nav.storage.state import fingerprint

    from aiogram_idle.errors import ActivityConflict
    from aiogram_idle.models import freeze_object

    backend = combined_backend
    idle, integration, nav, _ = build(backend)
    await nav.for_conversation(KEY).go("editor", params={"draft_id": True}, operation_id="entry")
    repo = integration.navigation_repository
    mapped = repo.mapping.to_idle(KEY)
    async with idle.coordinator.hold(mapped):
        old = await backend.load(mapped)
        old = await backend.transition(
            mapped,
            expected_version=old.version,
            operation_id="reserve-forged",
            fingerprint="reserve-forged",
            transform=lambda value: replace(
                value,
                idle=IdleSnapshot(
                    phase=Phase.RESUMING,
                    operation=PendingOperation(
                        "answer", "continue", started_at=backend.clock.now()
                    ),
                ),
            ),
        )
        effects = OperationEffects(idle, mapped, "answer", None)
        context = FlowContext(mapped, old.activity, "answer", backend.clock.now(), effects=effects)
        receipt = await idle.adapters["aiogram_nav"].resume(context, operation_id="answer")
        old = await backend.load(mapped)
        component = dict(receipt.component_updates["aiogram_nav"])
        if backend.active_storage_format == 3:
            # Canonical receipts contain only an operation reference. They cannot
            # submit a rewritten target, history row, or current draft snapshot.
            # Test the same untrusted-adapter boundary using that wire contract.
            if corruption == "target":
                component["canonical_stage"] = "foreign-answer"
            elif corruption == "retained_receipt":
                component["ledger"] = {"entry": {"retention_until": 999999999}}
            else:
                component["current_params"] = {"draft_id": 1}
            updates = {**receipt.component_updates, "aiogram_nav": component}
            forged = replace(receipt, component_updates=freeze_object(updates, max_bytes=8_388_608))
            with pytest.raises(ActivityConflict, match="staged operation reference"):
                await repo.complete_canonical(old, old, forged, None, None)
            assert (await repo.load(KEY)).snapshot.node_id == "editor"
            return
        ledger = loads(component["ledger"], KEY)
        if corruption == "target":
            action = ledger.operations["answer"]
            intent = replace(action.prepared.intent, node_id="main", params={})
            digest = fingerprint(intent)
            action.fingerprint = digest
            action.prepared = replace(action.prepared, intent=intent, fingerprint=digest)
            snapshot = replace(action.result.snapshot, node_id="main", params={})
            action.result = replace(action.result, snapshot=snapshot)
            ledger.current = replace(ledger.current, snapshot=snapshot)
        elif corruption == "retained_receipt":
            ledger.operations["entry"].retention_until += 1000
        else:
            ledger.current = replace(
                ledger.current, snapshot=replace(ledger.current.snapshot, params={"draft_id": 1})
            )
        component["ledger"] = dumps(KEY, ledger)
        # This is a valid self-consistent DTO envelope, but it is not the
        # completion of the persisted reservation that authorized rendering.
        assert loads(component["ledger"], KEY).pending_id is None
        updates = {**receipt.component_updates, "aiogram_nav": component}
        forged = replace(receipt, component_updates=freeze_object(updates, max_bytes=8_388_608))
        changed = replace(
            old, components=freeze_object({**old.components, **updates}, max_bytes=8_388_608)
        )
        with pytest.raises(
            ActivityConflict, match="reserved navigation identity|retained operation evidence"
        ):
            repo.finalize(old, changed, forged)
        assert (await repo.load(KEY)).snapshot.node_id == "editor"


async def test_integrated_completion_requires_staged_navigation_component(combined_backend):
    from aiogram_idle.errors import ActivityConflict
    from aiogram_idle.models import ActionReceipt

    idle, integration, nav, _ = build(combined_backend)
    await nav.for_conversation(KEY).go("editor", operation_id="entry")
    record = await combined_backend.load(integration.navigation_repository.mapping.to_idle(KEY))
    with pytest.raises(ActivityConflict, match="requires staged navigation"):
        integration.navigation_repository.finalize(record, record, ActionReceipt())
