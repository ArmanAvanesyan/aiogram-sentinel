"""One authority observation feeds the atomic navigation/activity projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from aiogram_coordination import ExternalSession
from aiogram_nav.errors import SessionExpired
from aiogram_nav.models import ConversationKey
from aiogram_nav.storage.memory import MemoryNavigationRepository

from ...errors import ActivityConflict, IdleError
from ...models import RuntimeSnapshot
from ...storage.session_bindings import EXTERNAL_SESSION
from .errors import navigation_error

if TYPE_CHECKING:
    from .repository import NavigationRepository


def binding(record: RuntimeSnapshot | None) -> Mapping[str, object] | None:
    value = record.components.get(EXTERNAL_SESSION) if record else None
    return value if isinstance(value, Mapping) else None


async def observe(repo: NavigationRepository, key: ConversationKey) -> ExternalSession | None:
    if repo.idle.session_authority is None:
        return None
    try:
        await repo.idle.backend.require_storage_format(2)
        return await repo.idle.external_session(repo.mapping.to_idle(key))
    except IdleError as error:
        raise navigation_error(error) from error


async def authorize(
    repo: NavigationRepository, key: ConversationKey, expected_session_id: str | None = None
) -> ExternalSession | None:
    session = await observe(repo, key)
    if session is None:
        return None
    record = await repo.idle.backend.load(repo.mapping.to_idle(key))
    if expected_session_id is not None:
        if record is None or record.session.session_id != expected_session_id:
            raise SessionExpired("Integrated session generation changed")
        try:
            await repo.idle.authorize(record, observation=session)
        except IdleError as error:
            raise navigation_error(error) from error
    return session


async def seed(
    repo: NavigationRepository,
    key: ConversationKey,
    current: RuntimeSnapshot | None,
    memory: MemoryNavigationRepository,
    session: ExternalSession | None,
) -> None:
    if session is None:
        return
    old = binding(current)
    changed = old is not None and old.get("session_id") != session.session_id
    if current is not None and (old is None or changed):
        if current.idle.operation is not None:
            raise ActivityConflict("Unresolved idle evidence prevents session rotation")
        if old is None and current.session.expires_at > repo.idle.clock.now():
            raise ActivityConflict("Cannot adopt an existing library-owned session")
    # The scratch backend is private to this one already-coordinated transaction.
    memory._storage_format = 2  # pyright: ignore[reportPrivateUsage]
    previous = await memory.external_session(key)
    source = (
        replace(session, revision=previous.revision)
        if previous and previous.session_id == session.session_id
        else session
    )
    await memory.bind_external_session(key, source)
