"""One-operation adoption never publishes a partially accepted activity."""

import pytest

from aiogram_nav import (
    ConversationKey,
    ManualClock,
    MemoryNavigationRepository,
    MessageRef,
    NavigationIntent,
    RenderResult,
    StaleView,
)

KEY = ConversationKey("test", 1, 2, 2)


def intent(operation="adopt", view="view"):
    return NavigationIntent(operation, "main", action="track", view_id=view)


async def test_failed_adoption_rolls_back_hot_state_and_new_operation():
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    result = await repo.adopt_render(
        KEY, expected_version=None, intent=intent(), rendered=RenderResult("view")
    )
    previous = await repo.load(KEY)
    with pytest.raises(StaleView):
        await repo.adopt_render(
            KEY,
            expected_version=previous.version,
            intent=intent("invalid", "new"),
            rendered=RenderResult("new", (MessageRef(999, 1),)),
        )
    assert await repo.load(KEY) == previous
    assert (await repo.lookup_operation(KEY, operation_id="invalid")).status == "not_found"
    assert await repo.pending(KEY) is None
    duplicate = await repo.adopt_render(
        KEY, expected_version="stale", intent=intent(), rendered=RenderResult("view")
    )
    assert duplicate.duplicate and duplicate.snapshot == result.snapshot


async def test_exception_after_pure_completion_rolls_back_all_accepted_state(monkeypatch):
    repo = MemoryNavigationRepository(clock=ManualClock(1000))
    await repo.adopt_render(
        KEY, expected_version=None, intent=intent(), rendered=RenderResult("view")
    )
    before = await repo.load(KEY)
    original = repo._commit_locked

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected after reducer completion")

    monkeypatch.setattr(repo, "_commit_locked", fail)
    with pytest.raises(RuntimeError):
        await repo.adopt_render(
            KEY,
            expected_version=before.version,
            intent=intent("second", "second"),
            rendered=RenderResult("second"),
        )
    assert await repo.load(KEY) == before
    assert (await repo.lookup_operation(KEY, operation_id="second")).status == "not_found"
    # Failed completion must not poison the fresh-view ownership index.
    monkeypatch.setattr(repo, "_commit_locked", original)
    accepted = await repo.adopt_render(
        KEY,
        expected_version=before.version,
        intent=intent("second", "second"),
        rendered=RenderResult("second"),
    )
    assert accepted.snapshot.view.view_id == "second"


async def test_custom_subclass_public_hooks_keep_legacy_path():
    from aiogram_nav import (
        ApplicationPresenter,
        CleanupResult,
        Navigation,
        NavigationRegistry,
        Node,
    )

    calls = []

    class ApplicationRepository(MemoryNavigationRepository):
        async def commit(self, *args, **kwargs):
            calls.append("public-commit-hook")
            return await super().commit(*args, **kwargs)

    async def cleanup(request):
        return CleanupResult()

    repo = ApplicationRepository(clock=ManualClock(1000))
    nav = Navigation(
        registry=NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="app")]),
        repository=repo,
        presenter=ApplicationPresenter(cleanup=cleanup),
        namespace="test",
    )
    await nav.for_conversation(KEY).track(
        "main", rendered=RenderResult("view"), operation_id="track"
    )
    assert calls == ["public-commit-hook"]
