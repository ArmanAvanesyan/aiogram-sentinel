"""Deterministic recovery accounting under an abandoned memory-poller lease."""

from __future__ import annotations

import pytest

from aiogram_idle import IdleConversationKey, OwnershipLost, Phase
from tests.runtime_helpers import make_harness


async def test_thousand_due_activities_survive_abandoned_claim_batch():
    h = await make_harness(lifetime=10_000)
    keys = [h.key]
    policy = h.runtime.policies["draft"]
    for user in range(3, 1002):
        key = IdleConversationKey("test", 1, user, user)
        keys.append(key)
        session = await h.backend.open_session(key, lifetime_seconds=10_000, operation_id="open")
        await h.backend.enter(
            key,
            "form",
            policy_id="draft",
            policy=policy,
            adapter_key="form",
            params={"draft_id": "draft"},
            session_id=session.session_id,
            expires_at=session.expires_at,
            operation_id="enter",
            enabled=True,
        )
    h.clock.advance(10)
    abandoned = await h.backend.claim_due(limit=137, lease_seconds=60, namespace="test")
    assert len(abandoned) == 137
    h.clock.advance(60)
    for claim in abandoned:
        with pytest.raises(OwnershipLost):
            await h.backend.validate_claim(claim)
    processed = 0
    while True:
        report = await h.runtime.run_once()
        if not report.claimed:
            break
        assert report.failed == 0
        processed += report.completed
    assert processed == len(keys) == len(h.presenter.questions) == 1000
    for key in keys:
        record = await h.backend.load(key)
        assert record.idle.phase is Phase.PROMPTED
        assert record.idle.deadline == 1090
