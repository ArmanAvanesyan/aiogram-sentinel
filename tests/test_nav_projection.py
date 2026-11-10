"""Optional projection contracts against memory and authoritative real Redis."""

from uuid import uuid4

import pytest

pytest.importorskip("aiogram_nav")
from aiogram_nav import (
    ConversationKey,
    Navigation,
    NavigationConfig,
    NavigationRegistry,
    Node,
    RenderResult,
)
from aiogram_nav.errors import PendingAction

from aiogram_idle import ExemptPolicy, IdleConfig, IdlePolicies, IdleRuntime, PromptPolicy
from aiogram_idle.clock import ManualClock
from aiogram_idle.errors import ActivityConflict
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_idle.storage.memory import MemoryIdleBackend
from tests.runtime_helpers import Adapter, Presenter

KEY = ConversationKey("default", 1, 42, 42)


class NavPresenter:
    replay_safe = True

    def __init__(self):
        self.calls = 0

    async def render(self, request):
        self.calls += 1
        return RenderResult(request.view_id)

    async def cleanup(self, request):
        pass


@pytest.fixture(params=["memory", "redis"])
async def integrated(request):
    kind, nav_config = request.param if isinstance(request.param, tuple) else (request.param, None)
    config = IdleConfig(enabled=True, poll_seconds=1)
    if kind == "memory":
        backend = MemoryIdleBackend(clock=ManualClock(), config=config)
    else:
        redis = pytest.importorskip("redis.asyncio")
        from aiogram_idle.storage.redis import RedisIdleBackend

        client = redis.Redis.from_url(request.getfixturevalue("redis_url"))
        backend = RedisIdleBackend(
            redis=client, prefix=f"nav-projection:{uuid4().hex}", config=config
        )
        await backend.initialize()
    runtime = IdleRuntime(
        backend=backend,
        config=config,
        policies=IdlePolicies(
            {"none": ExemptPolicy(), "draft": PromptPolicy(after_seconds=10, grace_seconds=10)}
        ),
        adapters={"unused": Adapter()},
        presenter=Presenter(backend.clock),
    )
    registry = NavigationRegistry(
        roots={"main"},
        nodes=[
            Node("main", renderer="screen"),
            Node("form", parent="main", renderer="screen"),
            Node("form.step", parent="form", renderer="screen"),
        ],
    )
    integration = NavigationIntegration(
        idle=runtime,
        registry=registry,
        config=nav_config,
        policies=NodePolicies(
            default="none",
            overrides={"form": "draft"},
            activities={"form": "draft", "form.step": "draft"},
        ),
    )
    presenter = NavPresenter()
    navigation = Navigation(
        registry=registry, repository=integration.navigation_repository, presenter=presenter
    )
    integration.bind(navigation)
    yield integration, navigation, backend, presenter
    await backend.close()
    if kind == "redis":
        await client.aclose()


async def state(integration, backend):
    return await backend.load(integration.navigation_repository.mapping.to_idle(KEY))


async def test_navigation_and_activity_commit_one_atomic_record(integrated):
    integration, nav, backend, presenter = integrated
    context = nav.for_conversation(KEY)
    await context.go("form", operation_id="enter")
    current = await context.current()
    stored = await state(integration, backend)
    assert stored.activity.session_id == current.session_id == stored.session.session_id
    assert stored.activity.activity_revision == current.activity_revision == 1
    assert stored.activity.activity_key == "draft" and stored.activity.policy_id == "draft"
    assert stored.idle.deadline == stored.activity.last_activity_at + 10
    await context.go("form.step", operation_id="tab")
    next_state = await state(integration, backend)
    assert next_state.activity.activity_id == stored.activity.activity_id
    assert next_state.activity.activity_revision == 2
    await context.go("main", operation_id="home")
    exempt = await state(integration, backend)
    assert exempt.activity.activity_id != next_state.activity.activity_id
    assert exempt.activity.activity_revision == 3
    assert exempt.idle.deadline is None
    assert presenter.calls == 3


async def test_guarded_touch_keeps_both_acceptance_counters_coherent(integrated):
    integration, nav, backend, _ = integrated
    await nav.for_conversation(KEY).go("form", operation_id="enter")
    before = await state(integration, backend)
    touched = await integration.touch(KEY, expected=before.activity.guard, operation_id="text")
    assert touched.activity_revision == 2
    assert (await nav.for_conversation(KEY).current()).activity_revision == 2
    duplicate = await integration.touch(KEY, expected=before.activity.guard, operation_id="text")
    assert duplicate.activity_revision == 2
    with pytest.raises(ActivityConflict):
        await integration.touch(KEY, expected=before.activity.guard, operation_id="stale")
    with pytest.raises(ActivityConflict):
        await integration.idle.for_conversation(before.key).touch(
            expected=touched.guard, operation_id="wrong-writer"
        )


async def test_background_navigation_preserves_activity_and_deadline(integrated):
    integration, nav, backend, _ = integrated
    context = nav.for_conversation(KEY)
    await context.go("form", operation_id="enter")
    before = await state(integration, backend)
    await context.go("form.step", operation_id="background", accepted_activity=False)
    after = await state(integration, backend)
    assert after.activity == before.activity and after.idle.deadline == before.idle.deadline
    assert (await context.current()).activity_revision == before.activity.activity_revision


async def test_prepare_reserves_recovery_without_accepting_activity(integrated):
    integration, nav, backend, _ = integrated
    context = nav.for_conversation(KEY)
    await context.go("form", operation_id="enter")
    before = await state(integration, backend)
    await context.prepare_render("main", operation_id="pending")
    pending = await state(integration, backend)
    assert pending.activity == before.activity
    assert pending.components["__idle_owner__"]["pending"] is True
    with pytest.raises(PendingAction):
        await context.go("form", operation_id="other")
    await nav.recover(KEY, operation_id="pending")
    after = await state(integration, backend)
    assert after.components["__idle_owner__"]["pending"] is False
    assert after.activity.activity_revision == 2


async def test_authoritative_manifest_toggle_controls_new_navigation_deadlines(integrated):
    from aiogram_idle.models import ConfigUpdate

    integration, nav, backend, _ = integrated
    context = nav.for_conversation(KEY)
    await context.go("form", operation_id="first")
    manifest = await integration.idle.manifest()
    disabled = await integration.idle.apply_config(
        expected_generation=manifest.generation, update=ConfigUpdate(False, "off")
    )
    await context.go("form.step", operation_id="disabled")
    assert (await state(integration, backend)).idle.deadline is None
    await integration.idle.apply_config(
        expected_generation=disabled.generation, update=ConfigUpdate(True, "on")
    )
    await context.go("form", operation_id="reenabled")
    assert (await state(integration, backend)).idle.deadline is not None


async def test_successful_navigation_supersedes_prompt_cleanup_once(integrated):
    from dataclasses import replace

    from aiogram_idle.models import IdleSnapshot, Phase
    from aiogram_idle.presentation import PromptReceipt

    integration, nav, backend, _ = integrated
    await nav.for_conversation(KEY).go("form", operation_id="first")
    before = await state(integration, backend)
    prompt = PromptReceipt(
        "prompt", (), backend.clock.now(), "inline", "en", "cont", "cancel", before.key
    )
    await backend.transition(
        before.key,
        expected_version=before.version,
        operation_id="shown",
        fingerprint="shown",
        transform=lambda old: replace(
            old,
            idle=IdleSnapshot(
                phase=Phase.PROMPTED, deadline=backend.clock.now() + 100, prompt=prompt
            ),
        ),
    )
    await nav.for_conversation(KEY).go("main", operation_id="next")
    assert integration.idle.presenter.strips == [prompt]
    await nav.for_conversation(KEY).go("main", operation_id="next")
    assert integration.idle.presenter.strips == [prompt]
    assert (await state(integration, backend)).idle.prompt is None


@pytest.mark.parametrize("invalid", [None, True, 42, "", "x" * 129])
def test_policy_mapping_rejects_invalid_default(invalid):
    from aiogram_idle.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        NodePolicies(default=invalid)


def test_custom_identity_mapping_cannot_change_actual_actor():
    from dataclasses import replace

    from aiogram_idle.errors import ConfigurationError
    from aiogram_idle.integrations.nav.mapping import IdentityMapping, VerifiedIdentityMapping

    class WrongActor(IdentityMapping):
        def to_idle(self, key):
            original = super().to_idle(key)
            return replace(original, chat_id=43, user_id=43)

        def to_nav(self, key):
            return KEY

    with pytest.raises(ConfigurationError):
        VerifiedIdentityMapping(WrongActor()).to_idle(KEY)


@pytest.mark.parametrize(
    "integrated",
    [
        ("memory", NavigationConfig(session_seconds=2)),
        ("redis", NavigationConfig(session_seconds=2)),
    ],
    indirect=True,
)
async def test_navigation_expiry_inside_live_auth_session_allocates_fresh_activity(integrated):
    import asyncio

    integration, nav, backend, _ = integrated
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    session = await integration.idle.for_conversation(mapped).open_session(
        operation_id="auth", lifetime_seconds=10
    )
    await nav.for_conversation(KEY).go("form", operation_id="first")
    first = await state(integration, backend)
    if isinstance(backend.clock, ManualClock):
        backend.clock.advance(2.2)
    else:
        await asyncio.sleep(2.2)
    await nav.for_conversation(KEY).go("form", operation_id="next")
    after = await state(integration, backend)
    assert after.session == session
    assert after.activity.activity_id != first.activity.activity_id
    assert after.activity.activity_revision == 2
    latest = await nav.for_conversation(KEY).current()
    assert latest.activity_revision == 2 and latest.nav_revision == 2


async def test_old_touch_retry_returns_original_activity_receipt_after_new_navigation(integrated):
    integration, nav, backend, _ = integrated
    await nav.for_conversation(KEY).go("form", operation_id="entry")
    before = await state(integration, backend)
    accepted = await integration.touch(KEY, expected=before.activity.guard, operation_id="text")
    await nav.for_conversation(KEY).go("main", operation_id="move")
    current = await state(integration, backend)
    duplicate = await integration.touch(KEY, expected=before.activity.guard, operation_id="text")
    assert duplicate == accepted
    assert (await state(integration, backend)).activity == current.activity
    assert current.activity.activity_id != duplicate.activity_id


async def test_reply_overlay_invalidates_provenance_and_touch_restores_without_reacceptance(
    integrated,
):
    from dataclasses import replace

    from aiogram_idle.integrations.nav.codec import load_ledger
    from aiogram_idle.models import IdleSnapshot, Phase
    from aiogram_idle.presentation import PromptReceipt

    integration, nav, backend, presenter = integrated
    seen = []

    async def application_tray(request):
        presenter.calls += 1
        seen.append(request.current.view.reply_keyboard_key if request.current else None)
        return RenderResult(request.view_id, reply_keyboard_key="app", reply_keyboard_locale="en")

    presenter.render = application_tray
    await nav.for_conversation(KEY).go("form", operation_id="entry")
    mapped = integration.navigation_repository.mapping.to_idle(KEY)
    record = await backend.load(mapped)
    receipt = PromptReceipt(
        "shown", (), backend.clock.now(), "reply", "en", "cont", "cancel", mapped
    )
    await backend.transition(
        mapped,
        expected_version=record.version,
        operation_id="reply-shown",
        fingerprint="shown",
        transform=lambda old: replace(
            old,
            idle=IdleSnapshot(
                phase=Phase.PROMPTED, deadline=backend.clock.now() + 100, prompt=receipt
            ),
        ),
    )
    overlaid = await backend.load(mapped)
    projected = await nav.for_conversation(KEY).current()
    assert projected.view.reply_keyboard_key is None
    assert projected.view.reply_keyboard_locale is None
    raw = load_ledger(overlaid, KEY, expected_profile=integration.navigation_repository.profile)
    assert raw.current.snapshot.view.reply_keyboard_key == "app"
    accepted = await integration.touch(KEY, expected=record.activity.guard, operation_id="input")
    restored = await backend.load(mapped)
    current = await nav.for_conversation(KEY).current()
    assert accepted.activity_revision == current.activity_revision == 2
    assert restored.activity.activity_id == record.activity.activity_id
    assert (
        restored.idle.prompt is None and restored.components["__idle_owner__"]["pending"] is False
    )
    assert restored.components["aiogram_nav"]["reply_overlay"] is False
    assert current.view.reply_keyboard_key == "app"
    assert seen == [None, None]
    await integration.touch(KEY, expected=record.activity.guard, operation_id="input")
    assert presenter.calls == 2


async def test_touch_overlay_recovery_survives_crash_before_eager_render(integrated, monkeypatch):
    from dataclasses import replace

    from aiogram_idle.models import IdleSnapshot, Phase
    from aiogram_idle.presentation import PromptReceipt

    integration, nav, backend, presenter = integrated
    repo = integration.navigation_repository

    async def screen(request):
        presenter.calls += 1
        return RenderResult(request.view_id, reply_keyboard_key="app", reply_keyboard_locale="en")

    presenter.render = screen
    await nav.for_conversation(KEY).go("form", operation_id="entry")
    mapped = repo.mapping.to_idle(KEY)
    before = await backend.load(mapped)
    prompt = PromptReceipt(
        "overlay", (), backend.clock.now(), "reply", "en", "cont", "cancel", mapped
    )
    await backend.transition(
        mapped,
        expected_version=before.version,
        operation_id="shown-overlay",
        fingerprint="shown-overlay",
        transform=lambda old: replace(
            old,
            idle=IdleSnapshot(
                phase=Phase.PROMPTED, deadline=backend.clock.now() + 100, prompt=prompt
            ),
        ),
    )
    original = repo._recover_overlay

    async def process_exit(key, operation_id):
        raise InterruptedError("simulated process exit after atomic touch")

    monkeypatch.setattr(repo, "_recover_overlay", process_exit)
    with pytest.raises(InterruptedError):
        await integration.touch(KEY, expected=before.activity.guard, operation_id="accepted")
    committed = await backend.load(mapped)
    assert committed.activity.activity_revision == 2 and committed.idle.prompt is None
    assert committed.components["__idle_owner__"]["pending"] is True
    assert committed.components["aiogram_nav"]["reply_overlay"] is True
    assert (await nav.for_conversation(KEY).current()).view.reply_keyboard_key is None
    monkeypatch.setattr(repo, "_recover_overlay", original)
    owner = dict(committed.components["__idle_owner__"])
    owner["recovery_at"] = backend.clock.now() - 1
    await backend.transition(
        mapped,
        expected_version=committed.version,
        operation_id="wake-recovery",
        fingerprint="wake-recovery",
        transform=lambda old: replace(old, components={**old.components, "__idle_owner__": owner}),
    )
    assert (await integration.idle.run_once()).completed == 1
    recovered = await backend.load(mapped)
    assert recovered.activity.activity_revision == 2
    assert recovered.components["__idle_owner__"]["pending"] is False
    assert (await nav.for_conversation(KEY).current()).view.reply_keyboard_key == "app"
    assert presenter.calls == 2
