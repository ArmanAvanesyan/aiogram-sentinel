"""Unknown optional component formats park without interpreting opaque state."""

from dataclasses import replace

import pytest

pytest.importorskip("aiogram_nav")

from aiogram_idle.models import freeze_object
from tests.test_nav_projection import KEY
from tests.test_nav_projection import integrated as integrated


@pytest.mark.parametrize("damage", ["future_schema", "boolean_schema", "malformed_ledger"])
async def test_unsupported_component_recovery_parks_once_without_changing_payload(
    integrated, damage
):
    integration, nav, backend, presenter = integrated
    await nav.for_conversation(KEY).prepare_render("form", operation_id="prepared")
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    record = await backend.load(mapped)
    corrupted = dict(record.components["aiogram_nav"])
    if damage == "future_schema":
        corrupted["schema"] = 2
    elif damage == "boolean_schema":
        corrupted["schema"] = True
    else:
        corrupted["ledger"] = "opaque unsupported ledger bytes"
    marker = dict(record.components["__idle_owner__"])
    marker["recovery_at"] = backend.clock.now() - 1
    await backend.transition(
        mapped,
        expected_version=record.version,
        operation_id="damage",
        fingerprint=damage,
        transform=lambda old: replace(
            old,
            components=freeze_object(
                {**old.components, "aiogram_nav": corrupted, "__idle_owner__": marker},
                max_bytes=8_388_608,
            ),
        ),
    )
    opaque = (await backend.load(mapped)).components["aiogram_nav"]
    report = await integration.idle.run_once()
    assert report.claimed == 1 and report.failed == 0
    parked = await backend.load(mapped)
    assert parked.components["aiogram_nav"] == opaque
    assert parked.components["__idle_owner__"]["pending"] is True
    assert parked.components["__idle_owner__"]["parked"] is True
    assert parked.components["__idle_owner__"]["failure_reason"] == "SchemaUnsupported"
    assert presenter.calls == 0
    assert (await integration.idle.run_once()).claimed == 0
