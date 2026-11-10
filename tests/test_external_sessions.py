"""Application authority is read-only and cannot erase uncertain local work."""

import pytest
from aiogram_coordination import ExternalSession, SessionAuthorityUnavailable

from aiogram_nav import ConfigurationError, PersistenceUnavailable, SessionExpired
from tests.test_navigation import KEY, harness


class Authority:
    def __init__(self, session):
        self.value = session
        self.failure = None
        self.keys = []

    async def current(self, key):
        self.keys.append(key)
        if self.failure:
            raise self.failure
        return self.value


async def activated():
    nav, ctx, presenter, clock = harness()
    await nav.repository.activate_storage_format(
        operation_id="upgrade", old_workers_drained=True, dry_run=False
    )
    return nav, ctx, presenter, clock


async def test_external_session_requires_explicit_format_activation():
    nav, ctx, presenter, _ = harness()
    nav.session_authority = Authority(ExternalSession("app", "1", 800000))
    with pytest.raises(ConfigurationError, match="activate"):
        await ctx.go("main", operation_id="unactivated")
    assert presenter.requests == []


async def test_external_expiry_is_absolute_and_source_idle_deadline_revokes_resume():
    nav, ctx, presenter, clock = await activated()
    authority = Authority(ExternalSession("app", "1", 800000, 300000))
    nav.session_authority = authority
    await ctx.go("main", operation_id="initial")
    current = await ctx.current()
    assert current.expires_at == 800000
    assert current.session_id != "app"
    authority.value = ExternalSession("app", "2", 800000, 500000)
    await ctx.go("a", operation_id="renewed-by-app")
    assert (await ctx.current()).expires_at == 800000
    clock.advance(500000)
    with pytest.raises(SessionExpired):
        await ctx.go("b", operation_id="expired")
    assert len(presenter.requests) == 2
    assert await ctx.current() is None


async def test_authority_outage_does_not_clear_current_or_confirm_work():
    nav, ctx, presenter, _ = await activated()
    authority = Authority(ExternalSession("app", "1", 800000))
    nav.session_authority = authority
    await ctx.go("main", operation_id="initial")
    before = (await nav.repository.load(KEY)).snapshot
    authority.failure = SessionAuthorityUnavailable("offline")
    with pytest.raises(PersistenceUnavailable):
        await ctx.go("a", operation_id="unavailable")
    assert (await nav.repository.load(KEY)).snapshot == before
    assert len(presenter.requests) == 1


async def test_replacement_preserves_receipts_and_unknown_work_blocks_rebinding():
    nav, ctx, _, _ = await activated()
    authority = Authority(ExternalSession("first", "1", 800000))
    nav.session_authority = authority
    await ctx.go("main", operation_id="initial")
    old = await ctx.current()
    authority.value = ExternalSession("second", "1", 900000)
    await ctx.go("a", operation_id="second")
    assert (await ctx.current()).session_id != old.session_id
    assert (
        await nav.repository.lookup_operation(KEY, operation_id="initial")
    ).status == "completed"
    await ctx.prepare_action("go", node_id="b", operation_id="uncertain")
    authority.value = ExternalSession("third", "1", 950000)
    from aiogram_nav import PendingAction

    with pytest.raises(PendingAction):
        await ctx.go("main", operation_id="third")
    assert (await nav.pending(KEY)).operation_id == "uncertain"


async def test_same_application_id_cannot_extend_absolute_expiry():
    nav, ctx, _, _ = await activated()
    authority = Authority(ExternalSession("app", "1", 800000))
    nav.session_authority = authority
    await ctx.go("main", operation_id="initial")
    authority.value = ExternalSession("app", "2", 900000)
    with pytest.raises(ConfigurationError, match="Absolute"):
        await ctx.go("a", operation_id="invalid-extension")


async def test_revoked_authority_preserves_confirmed_manual_render_without_cleanup():
    from aiogram_nav import MessageRef, RenderResult

    nav, ctx, presenter, _ = await activated()
    authority = Authority(ExternalSession("app", "1", 800000))
    nav.session_authority = authority
    await ctx.go("main", operation_id="initial")
    prepared = await ctx.prepare_action("go", node_id="a", operation_id="sent")
    authority.value = None
    with pytest.raises(SessionExpired):
        await ctx.complete_render(
            prepared, rendered=RenderResult(prepared.view_id, (MessageRef(KEY.chat_id, 999),))
        )
    retained = await nav.repository.lookup_operation(KEY, operation_id="sent")
    assert retained.prepared.effects["render"].state == "confirmed"
    assert (await nav.repository.load(KEY)).snapshot.node_id == "main"
    assert len(presenter.cleanups) == 1


async def test_activated_memory_accepts_new_read_only_assessment():
    from aiogram_nav import MemoryNavigationRepository

    repo = MemoryNavigationRepository()
    await repo.activate_storage_format(
        operation_id="apply", dry_run=False, old_workers_drained=True
    )
    report = await repo.activate_storage_format(operation_id="later-assessment")
    assert report.before == report.after == 2 and not report.applied
