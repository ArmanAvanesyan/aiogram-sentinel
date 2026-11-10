"""External session authority is read-only; local recovery evidence remains owned."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from aiogram_coordination import ExternalSession, SessionAuthorityUnavailable, coordination_key

from .errors import ConfigurationError, PersistenceUnavailable, SessionExpired
from .models import ConversationKey

if TYPE_CHECKING:
    from .navigation import Navigation


@runtime_checkable
class SessionRepository(Protocol):
    def require_storage_format(self, version: int) -> None: ...
    async def external_session(self, key: ConversationKey) -> ExternalSession | None: ...
    async def bind_external_session(
        self,
        key: ConversationKey,
        session: ExternalSession,
        *,
        coordination_scope: object | None = None,
    ) -> None: ...


SessionValidator = Callable[[ConversationKey, str | None], Awaitable[ExternalSession | None]]


async def authorize_session(
    nav: Navigation, key: ConversationKey, expected_session_id: str | None = None
) -> ExternalSession | None:
    if nav.session_validator is not None:
        return await nav.session_validator(key, expected_session_id)
    authority = nav.session_authority
    if authority is None:
        return None
    loaded = await nav.repository.load(key)
    repository = nav.repository
    if not isinstance(repository, SessionRepository):
        raise ConfigurationError("Repository does not support application session bindings")
    repository.require_storage_format(2)
    try:
        session = await authority.current(coordination_key(key))
    except SessionAuthorityUnavailable as error:
        raise PersistenceUnavailable("Application session authority is unavailable") from error
    if session is not None and not isinstance(cast(object, session), ExternalSession):
        raise ConfigurationError("Session authority returned an invalid session")
    if session is None or not session.is_live(nav.clock.now()):
        raise SessionExpired("No live authorized application session exists")
    binding = await repository.external_session(key)
    if expected_session_id is not None:
        pending = await nav.repository.pending(key)
        generation_matches = (
            loaded is not None and loaded.snapshot.session_id == expected_session_id
        ) or (pending is not None and pending.session_id == expected_session_id)
        if not generation_matches or binding is None or binding.session_id != session.session_id:
            raise SessionExpired("Application session generation changed")
    await repository.bind_external_session(
        key, session, coordination_scope=nav.coordinator.scope_token(key)
    )
    return session
