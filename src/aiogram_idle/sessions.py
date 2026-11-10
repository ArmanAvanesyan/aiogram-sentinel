"""Read-only authorization over application sessions, independent of navigation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from aiogram_coordination import ExternalSession, coordination_key

from .errors import ConfigurationError, SessionAuthorityUnavailable, SessionExpired
from .models import IdleConversationKey, Phase, RuntimeSnapshot
from .storage.session_bindings import EXTERNAL_SESSION

if TYPE_CHECKING:
    from .runtime import IdleRuntime
    from .storage.state import Claim


async def current_external(runtime: IdleRuntime, key: IdleConversationKey) -> ExternalSession:
    authority = runtime.session_authority
    if authority is None:
        raise ConfigurationError("No external session authority is configured")
    try:
        session = await authority.current(coordination_key(key))
    except Exception as error:
        raise SessionAuthorityUnavailable("Application session authority is unavailable") from error
    if session is None:
        raise SessionExpired("No authorized application session")
    if not isinstance(cast(object, session), ExternalSession):
        raise ConfigurationError("Session authority returned an invalid observation")
    if not session.is_live(int(runtime.clock.now() * 1000)):
        raise SessionExpired("Application session expired")
    return session


async def authorize(
    runtime: IdleRuntime, record: RuntimeSnapshot, *, observation: ExternalSession | None = None
) -> ExternalSession | None:
    if runtime.session_authority is None:
        if EXTERNAL_SESSION in record.components:
            raise ConfigurationError("Externally bound records require SessionAuthority")
        return None
    session = (
        observation if observation is not None else await current_external(runtime, record.key)
    )
    if not session.is_live(int(runtime.clock.now() * 1000)):
        raise SessionExpired("Application session expired")
    binding = record.components.get(EXTERNAL_SESSION)
    if (
        not isinstance(binding, Mapping)
        or binding.get("session_id") != session.session_id
        or binding.get("absolute_expires_at") != session.absolute_expires_at
    ):
        raise SessionExpired("Activity belongs to a retired application session")
    return session


async def retire(
    runtime: IdleRuntime, record: RuntimeSnapshot, *, claim: Claim | None = None
) -> RuntimeSnapshot:
    """Disable old work without running adapters or deleting recovery evidence."""
    from .effects import internal_id

    operation = record.idle.operation
    phase = Phase.QUARANTINED if operation is not None else Phase.DISARMED
    changed = replace(record.idle, phase=phase, deadline=None)
    operation_id = internal_id(
        record.session.session_id, f"authority-expired:{record.store_version}"
    )
    committed = await runtime.backend.transition(
        record.key,
        expected_version=record.store_version,
        operation_id=operation_id,
        fingerprint=operation_id,
        claim=claim,
        coordination_scope=runtime.coordinator.scope_token(record.key),
        transform=lambda old: replace(old, idle=changed),
    )
    await runtime.notify(committed, "session_expired", operation_id)
    return committed
