"""All action kinds share authorized prepare/render/complete semantics."""

import pytest

from aiogram_nav.clock import ManualClock
from aiogram_nav.config import NavigationConfig
from aiogram_nav.errors import AccessDenied, ConfigurationError, OperationIdConflict
from aiogram_nav.models import ConversationKey, MessageRef, Node, RenderResult
from aiogram_nav.navigation import Navigation
from aiogram_nav.registry import NavigationRegistry
from aiogram_nav.rendering.base import CleanupResult
from aiogram_nav.storage.memory import MemoryNavigationRepository

KEY = ConversationKey("default", 1, 2, 2)


class Presenter:
    def __init__(self):
        self.requests = []
        self.cleanups = []
        self.failure = None

    async def render(self, request):
        self.requests.append(request)
        if self.failure:
            raise self.failure
        return RenderResult(
            request.view_id,
            (MessageRef(request.key.chat_id, len(self.requests)),),
            locale=request.locale,
        )

    async def cleanup(self, request):
        self.cleanups.append(request)
        return CleanupResult()


def harness(*, authorize=None, cancel_hook=None, on_event=None, roots=None, nodes=None, **kwargs):
    config = NavigationConfig(session_seconds=100, history_limit=3)
    clock = ManualClock(1000)
    repository = MemoryNavigationRepository(config=config, clock=clock)
    presenter = Presenter()
    registry = NavigationRegistry(
        roots=roots or {"main"},
        nodes=nodes
        or [
            Node("main", renderer="main"),
            Node("a", parent="main", renderer="a", cancel_to="main"),
            Node("b", parent="a", renderer="b"),
            Node("c", parent="b", renderer="c", back_to="main"),
        ],
    )
    nav = Navigation(
        registry=registry,
        repository=repository,
        presenter=presenter,
        config=config,
        authorize=authorize,
        cancel_hook=cancel_hook,
        on_event=on_event,
        **kwargs,
    )
    return nav, nav.for_conversation(KEY), presenter, clock


async def test_go_revisions_touch_and_deduplicated_retry():
    nav, ctx, presenter, _ = harness()
    first = await ctx.go("main", operation_id="first")
    current = await ctx.current()
    assert current.nav_revision == current.activity_revision == 1
    assert await ctx.go("main", operation_id="first") == first
    assert len(presenter.requests) == 1
    await ctx.go("a", params={"page": 2}, operation_id="second")
    current = await ctx.current()
    assert current.nav_revision == current.activity_revision == 2
    touched = await ctx.touch(source="typing", operation_id="typing")
    assert touched.nav_revision == 2 and touched.activity_revision == 3
    assert await ctx.touch(source="typing", operation_id="typing") == touched
    assert touched.expires_at == current.expires_at
    assert not await nav.is_busy(KEY)


async def test_history_back_and_root_back_does_not_push_history():
    _, ctx, presenter, _ = harness()
    for node in ["main", "a", "b"]:
        await ctx.go(node, operation_id=node)
    await ctx.back(operation_id="back")
    assert (await ctx.current()).node_id == "a"
    assert [entry.node_id for entry in (await ctx.current()).history] == ["main"]
    await ctx.back(operation_id="back-again")
    assert (await ctx.current()).node_id == "main"
    await ctx.back(operation_id="root-back")
    assert (await ctx.current()).history == ()
    assert len(presenter.requests) == 6


async def test_explicit_back_and_inherited_cancel_do_not_clear_application_draft():
    draft = {"text": "retained"}
    _, ctx, _, _ = harness()
    await ctx.go("main", operation_id="main")
    await ctx.go("b", operation_id="b")
    await ctx.cancel(operation_id="cancel")
    assert (await ctx.current()).node_id == "main"
    assert draft == {"text": "retained"}
    await ctx.go("c", operation_id="c")
    await ctx.back(operation_id="explicit")
    assert (await ctx.current()).node_id == "main"


async def test_cancel_hook_only_runs_for_cancel_and_once_per_operation():
    calls = []

    async def cancel(request):
        calls.append(request.operation_id)
        return {"cleared": True}

    _, ctx, _, _ = harness(cancel_hook=cancel)
    await ctx.go("main", operation_id="main")
    await ctx.go("a", operation_id="a")
    await ctx.back(operation_id="back")
    assert calls == []
    await ctx.cancel(operation_id="cancel")
    await ctx.cancel(operation_id="cancel")
    assert calls == ["cancel"]


async def test_authorization_rechecked_for_direct_actions_refresh_and_recovery():
    allowed = True

    async def authorize(key, node, params, source):
        return allowed

    nav, ctx, presenter, _ = harness(authorize=authorize)
    await ctx.go("a", operation_id="a")
    allowed = False
    with pytest.raises(AccessDenied):
        await ctx.refresh(operation_id="refresh")
    with pytest.raises(AccessDenied):
        await nav.recover(KEY, operation_id="a")
    assert len(presenter.requests) == 1


async def test_operation_reuse_with_other_destination_or_params_rejected():
    _, ctx, _, _ = harness()
    await ctx.go("a", params={"p": 1}, operation_id="same")
    with pytest.raises(OperationIdConflict):
        await ctx.go("b", operation_id="same")
    with pytest.raises(OperationIdConflict):
        await ctx.go("a", params={"p": 2}, operation_id="same")


async def test_background_refresh_preserves_activity_and_absolute_expiry():
    _, ctx, _, clock = harness()
    await ctx.go("a", operation_id="a")
    old = await ctx.current()
    clock.advance(500)
    await ctx.refresh(operation_id="background", accepted_activity=False)
    new = await ctx.current()
    assert new.nav_revision == old.nav_revision + 1
    assert new.activity_revision == old.activity_revision
    assert new.last_activity_at == old.last_activity_at and new.expires_at == old.expires_at


async def test_expired_session_gets_fresh_generation_and_no_retained_history():
    _, ctx, _, clock = harness()
    await ctx.go("a", operation_id="first")
    old = await ctx.current()
    clock.advance(100001)
    assert await ctx.current() is None
    await ctx.go("main", operation_id="new-session")
    new = await ctx.current()
    assert new.session_id != old.session_id and new.history == ()


async def test_prepare_complete_and_track_do_not_send():
    nav, ctx, presenter, _ = harness()
    prepared = await ctx.prepare_render("a", operation_id="prepared")
    assert await ctx.current() is None
    rendered = RenderResult(prepared.view_id, (MessageRef(2, 30),))
    done = await ctx.complete_render(prepared, rendered=rendered)
    assert done.node_id == "a"
    assert await ctx.complete_render(prepared, rendered=rendered) == done
    tracked = await ctx.track(
        "b", rendered=RenderResult("external", (MessageRef(2, 31),)), operation_id="track"
    )
    assert tracked.node_id == "b" and tracked.view.view_id == "external"
    assert presenter.requests == []
    assert not await nav.is_busy(KEY)


async def test_multi_root_context_preserves_own_root_without_guessing():
    _, ctx, _, _ = harness(
        roots={"main", "welcome"},
        nodes=[
            Node("main", renderer="main"),
            Node("welcome", renderer="welcome"),
            Node("guest", parent="welcome", renderer="guest"),
        ],
    )
    with pytest.raises(ConfigurationError):
        await ctx.home(operation_id="ambiguous")
    await ctx.go("guest", operation_id="guest")
    await ctx.home(operation_id="home")
    assert (await ctx.current()).node_id == "welcome"
    await ctx.home(root="main", operation_id="explicit-main")
    assert (await ctx.current()).node_id == "main"


async def test_stable_update_context_operation_ids_and_direct_ids_required():
    nav, ctx, presenter, _ = harness()
    with pytest.raises(ConfigurationError):
        await ctx.go("main")
    first = nav.for_conversation(KEY, operation_prefix="update:42")
    second = nav.for_conversation(KEY, operation_prefix="update:42")
    assert await first.go("main") == await second.go("main")
    assert len(presenter.requests) == 1


async def test_hook_failure_cannot_undo_commit_or_repeat_delivery():
    calls = []

    async def observe(event):
        calls.append(event)
        raise RuntimeError("telemetry unavailable")

    _, ctx, presenter, _ = harness(on_event=observe)
    await ctx.go("main", operation_id="go")
    await ctx.go("main", operation_id="go")
    assert (await ctx.current()).node_id == "main" and len(calls) == 1
    assert len(presenter.requests) == 1


async def test_back_skips_invalid_or_denied_history_entries():
    allowed = {"main", "a", "b"}

    async def authorize(key, node, params, source):
        return node.id in allowed

    _, ctx, _, _ = harness(authorize=authorize)
    for node in ["main", "a", "b"]:
        await ctx.go(node, operation_id=node)
    allowed.remove("a")
    await ctx.back(operation_id="back")
    current = await ctx.current()
    assert current.node_id == "main" and current.history == ()


async def test_prepare_rejects_abstract_nodes_before_effects():
    _, ctx, presenter, _ = harness(
        nodes=[Node("main", renderer="main"), Node("group", parent="main")]
    )
    with pytest.raises(ConfigurationError):
        await ctx.go("group", operation_id="invalid")
    assert presenter.requests == []


async def test_back_history_does_not_implicitly_cross_roots():
    _, ctx, _, _ = harness(
        roots={"main", "welcome"},
        nodes=[
            Node("main", renderer="main"),
            Node("welcome", renderer="welcome"),
            Node("linked", parent="main", renderer="linked"),
            Node("guest", parent="welcome", renderer="guest"),
        ],
    )
    await ctx.go("linked", operation_id="linked")
    await ctx.go("guest", operation_id="guest")
    await ctx.back(operation_id="back")
    assert (await ctx.current()).node_id == "welcome"


async def test_explicit_node_rename_preserves_valid_reconstruction_parameters():
    nav, ctx, presenter, _ = harness()
    await ctx.go("a", params={"page": 3}, operation_id="old")

    def require_page(params):
        if "page" not in params:
            raise ValueError("page required")
        return params

    registry = NavigationRegistry(
        roots={"main"},
        nodes=[
            Node("main", renderer="main"),
            Node("renamed", parent="main", renderer="a", validator=require_page),
        ],
        migrations={"a": "renamed"},
    )
    replacement = Navigation(registry=registry, repository=nav.repository, presenter=presenter)
    await replacement.for_conversation(KEY).refresh(operation_id="migrated")
    current = await replacement.for_conversation(KEY).current()
    assert current.node_id == "renamed" and current.params == {"page": 3}


async def test_unknown_node_safe_root_does_not_reuse_unknown_parameters():
    nav, ctx, presenter, _ = harness()
    await ctx.go("a", params={"old-draft-id": "opaque"}, operation_id="old")
    registry = NavigationRegistry(
        roots={"main"}, nodes=[Node("main", renderer="main")], safe_root="main"
    )
    replacement = Navigation(registry=registry, repository=nav.repository, presenter=presenter)
    await replacement.for_conversation(KEY).refresh(operation_id="safe")
    current = await replacement.for_conversation(KEY).current()
    assert current.node_id == "main" and current.params == {}
