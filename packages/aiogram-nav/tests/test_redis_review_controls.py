"""Review regressions for controls on pending views and stale render capabilities."""

from dataclasses import replace

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup
from aiogram.types import CallbackQuery, Update

from aiogram_nav import (
    CallbackEntry,
    EffectCheckpoint,
    InputBindings,
    MessageRef,
    NavigationAction,
    NavigationToken,
    OwnershipLost,
    RenderResult,
    RenderUnknown,
)
from aiogram_nav.effects import NavigationEffects
from tests.test_examples import ACTOR, BOT_USER, RecordingSession, incoming
from tests.test_navigation import Presenter
from tests.test_redis_backend import KEY
from tests.test_redis_recovery import navigation, repository


@pytest.mark.parametrize("previous_view", [False, True])
async def test_pending_inline_callback_never_strips_recoverable_partial_view(
    nav_redis_client, previous_view
):
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    dispatcher = Dispatcher(disable_fsm=True)
    repo = await repository(nav_redis_client)
    nav = navigation(repo, Presenter())
    nav.bind(InputBindings([CallbackEntry("main", "main", target="main")]))
    nav.install(dispatcher)
    key = replace(KEY, bot_id=bot.id)
    context = nav.for_conversation(key)
    try:
        if previous_view:
            await context.go("main", operation_id="initial")
        prepared = await context.prepare_render("panel", operation_id="partial")
        rendered = RenderResult(prepared.view_id, (MessageRef(key.chat_id, 99),))
        # The inline message was sent, while a separate hybrid tray has not yet
        # completed. Its reserved controls are intentionally inert until commit.
        await repo.checkpoint(
            key, operation_id="partial", effect=EffectCheckpoint("text.content", "started")
        )
        await repo.checkpoint(
            key,
            operation_id="partial",
            effect=EffectCheckpoint("text.content", "confirmed", {"message_id": 99}),
        )
        token = NavigationToken(
            "A" * 24,
            key,
            key.user_id,
            prepared.session_id,
            prepared.view_id,
            NavigationAction(target="main"),
            prepared.expires_at,
            "main",
        )
        await repo.reserve_token(key, token, operation_id="partial:control")
        callback = CallbackQuery(
            id="early",
            from_user=ACTOR,
            chat_instance="test",
            message=incoming("partially rendered", 99).model_copy(update={"from_user": BOT_USER}),
            data=f"nav:{token.token}",
        )
        await dispatcher.feed_update(bot, Update(update_id=1, callback_query=callback))
        assert any(isinstance(method, AnswerCallbackQuery) for method in session.methods)
        assert not any(isinstance(method, EditMessageReplyMarkup) for method in session.methods)
        assert (await repo.pending(key)).operation_id == "partial"
        await nav.complete(prepared, rendered=rendered)
        assert (await context.current()).node_id == "panel"
        # The same physical keyboard is usable once the recovered view commits.
        await dispatcher.feed_update(
            bot,
            Update(update_id=2, callback_query=callback.model_copy(update={"id": "accepted"})),
        )
        assert (await context.current()).node_id == "main"
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_expired_recorder_cannot_confirm_under_reconstructed_owner(nav_redis_client):
    repo = await repository(nav_redis_client)
    nav = navigation(repo, Presenter())
    async with nav.coordinator.hold(KEY):
        prepared = await nav.prepare(KEY, "main", operation_id="reserved")
        recorder = NavigationEffects(nav, prepared)
        await recorder.checkpoint("render", "started")
    other_repo = await repository(nav_redis_client, repo.prefix)
    other = navigation(other_repo, Presenter())
    async with other.coordinator.hold(KEY):
        with pytest.raises(OwnershipLost):
            await recorder.checkpoint("render", "confirmed", RenderResult(prepared.view_id))
    with pytest.raises(RenderUnknown):
        await other.recover(KEY, operation_id="reserved")
    assert (await other_repo.pending(KEY)).effects["render"].state == "started"


async def test_unknown_callback_does_not_strip_an_untracked_bot_message(nav_redis_client):
    session = RecordingSession()
    bot = Bot("123456:ABC", session=session)
    dispatcher = Dispatcher(disable_fsm=True)
    repo = await repository(nav_redis_client)
    nav = navigation(repo, Presenter())
    nav.bind(InputBindings([CallbackEntry("main", "main", target="main")]))
    nav.install(dispatcher)
    key = replace(KEY, bot_id=bot.id)
    try:
        await nav.for_conversation(key).go("main", operation_id="main")
        callback = CallbackQuery(
            id="foreign-component",
            from_user=ACTOR,
            chat_instance="test",
            message=incoming("another component's keyboard", 999).model_copy(
                update={"from_user": BOT_USER}
            ),
            data="nav:" + "Z" * 24,
        )
        await dispatcher.feed_update(bot, Update(update_id=1, callback_query=callback))
        assert any(isinstance(method, AnswerCallbackQuery) for method in session.methods)
        assert not any(isinstance(method, EditMessageReplyMarkup) for method in session.methods)
        assert (await nav.for_conversation(key).current()).node_id == "main"
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()


async def test_revoked_owner_never_starts_post_commit_cleanup(nav_redis_client):
    import asyncio

    from aiogram_nav.storage.redis_coordinator import RedisCoordinator

    revoke_ready = asyncio.Event()

    class ObserverCoordinator(RedisCoordinator):
        async def _renew(self, *args):
            # Exercise revocation during the observer, rather than a short lease
            # or I/O timeout expiring incidentally during preparation on CI.
            await revoke_ready.wait()
            await super()._renew(*args)

    repo = await repository(nav_redis_client)
    coordinator = ObserverCoordinator(
        redis=nav_redis_client,
        prefix=repo.prefix,
        renew_seconds=0.05,
    )
    repo._store.coordinator = coordinator
    repo.coordinator = coordinator
    presenter = Presenter()
    nav = navigation(repo, presenter)
    cancelled = False
    revoked = False

    async def observer(event):
        nonlocal cancelled, revoked
        try:
            # The cancellation handler must already cover the await that deletes
            # the lock: a renewal can observe that deletion before its response.
            await nav_redis_client.delete(coordinator.lock_key(KEY))
            revoke_ready.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # A caller hook cannot restore the revoked lease by suppressing its
            # cancellation. New post-commit cleanup must still remain forbidden.
            cancelled = True
            revoked = not coordinator.owns(KEY)

    nav.on_event = observer
    with pytest.raises(OwnershipLost):
        await asyncio.wait_for(
            nav.for_conversation(KEY).go("main", operation_id="committed"), timeout=5
        )
    assert cancelled and revoked and presenter.cleanups == []
    assert (await repo.lookup_operation(KEY, operation_id="committed")).status == "completed"


async def test_reentrant_observer_navigation_skips_superseded_cleanup(nav_redis_client):
    repo = await repository(nav_redis_client)
    presenter = Presenter()
    nav = navigation(repo, presenter)

    async def observer(event):
        if event.operation_id == "outer":
            await nav.for_conversation(KEY).go("panel", operation_id="inner")

    nav.on_event = observer
    await nav.for_conversation(KEY).go("main", operation_id="outer")
    current = (await repo.load(KEY)).snapshot
    assert current.node_id == "panel"
    assert len(presenter.cleanups) == 1
    assert presenter.cleanups[0].current.view_id == current.view.view_id
    assert presenter.cleanups[0].ensure_owned is not None


async def test_cleanup_loop_rechecks_ownership_before_each_telegram_call(nav_redis_client):
    import asyncio

    from aiogram_nav import ViewState
    from aiogram_nav.rendering import CleanupRequest, TextPresenter
    from aiogram_nav.storage.redis_coordinator import RedisCoordinator

    repo = await repository(nav_redis_client)
    coordinator = RedisCoordinator(
        redis=nav_redis_client,
        prefix=repo.prefix,
        lease_seconds=0.3,
        renew_seconds=0.05,
        io_timeout=0.02,
    )

    class SlowCleanupSession(RecordingSession):
        async def make_request(self, bot, method, timeout=None):
            if isinstance(method, EditMessageReplyMarkup):
                await nav_redis_client.delete(coordinator.lock_key(KEY))
                try:
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    pass
            return await super().make_request(bot, method, timeout)

    session = SlowCleanupSession()
    # Cleanup uses KEY's bot id, unlike the dispatcher fixture bot.
    bot = Bot(f"{KEY.bot_id}:ABC", session=session)
    try:
        with pytest.raises(OwnershipLost):
            async with coordinator.hold(KEY):
                scope = coordinator.scope_token(KEY)

                def ensure_owned():
                    if scope is None or not coordinator.scope_matches(KEY, scope):
                        raise OwnershipLost("Cleanup lost its conversation lease")

                await TextPresenter({}, bot).cleanup(
                    CleanupRequest(
                        KEY,
                        ViewState("previous", (MessageRef(42, 11), MessageRef(42, 12))),
                        ViewState("current", (MessageRef(42, 99),)),
                        bot,
                        ensure_owned,
                    )
                )
        assert len(session.methods) == 1
        assert session.methods[0].message_id == 11
    finally:
        await bot.session.close()
