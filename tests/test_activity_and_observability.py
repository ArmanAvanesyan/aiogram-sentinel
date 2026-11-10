"""Small activity registrations and privacy-preserving observation adapters."""

from datetime import datetime, time, timezone

import pytest

from aiogram_idle import ActivityRegistration, IdleEvent, IdleOutcome, QuietHours, coarse_event_sink
from aiogram_idle.models import IdleConversationKey

KEY = IdleConversationKey("test", 123456, 42, 42)


@pytest.mark.parametrize("value", ["", "a" * 129, True])
def test_registration_validates_identifiers(value):
    with pytest.raises(ValueError):
        ActivityRegistration(value, "prompt", "form")


def test_registration_rejects_non_json_draft_values():
    with pytest.raises((TypeError, ValueError)):
        ActivityRegistration("form", "prompt", "form", {"object": object()})


async def test_coarse_sink_forwards_only_explicit_mapped_outcome_and_freezes_mapping():
    values = []

    async def sink(value):
        values.append(value)

    mapping = {"shown": "idle_shown"}
    observe = coarse_event_sink(sink, outcomes=mapping)
    mapping["shown"] = "changed"
    await observe(IdleEvent("id", "op", IdleOutcome.SHOWN, KEY, "private.node", 1000))
    await observe(IdleEvent("other", "op", "failed", KEY, "private.node", 1000))
    assert values == ["idle_shown"]


@pytest.mark.parametrize(
    "instant,expected",
    [
        ("2026-11-01T05:30:00+00:00", True),
        ("2026-11-01T06:30:00+00:00", True),  # Both repeated 01:30 instants.
        ("2026-11-01T07:00:00+00:00", False),
        ("2026-03-08T06:59:00+00:00", True),
        ("2026-03-08T07:00:00+00:00", False),  # Local clock jumps to 03:00.
    ],
)
async def test_quiet_hours_uses_instant_to_local_zone_across_dst(instant, expected):
    quiet = QuietHours("America/New_York", time(1), time(2))
    assert await quiet(KEY, datetime.fromisoformat(instant).timestamp()) is expected


async def test_quiet_resolver_can_select_per_conversation_zone():
    async def resolve(key, at):
        zone = "Asia/Yerevan" if key.user_id == 42 else "UTC"
        return await QuietHours(zone, time(22), time(7))(key, at)

    at = datetime(2026, 11, 10, 19, tzinfo=timezone.utc).timestamp()
    assert await resolve(KEY, at)
    assert not await resolve(IdleConversationKey("test", 123456, 43, 43), at)
