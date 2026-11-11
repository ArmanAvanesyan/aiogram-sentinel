"""Optional canonical-ledger adapter; storage owns opaque rows, navigation owns meaning."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, cast

from aiogram_nav.codec import encode as navigation_identity
from aiogram_nav.models import ConversationKey
from aiogram_nav.storage.ledger import LedgerRead
from aiogram_nav.storage.ledger_reducer import NavigationLedgerReducer

from ...models import (
    ActivitySnapshot,
    IdleConversationKey,
    JsonObject,
    RuntimeSnapshot,
    freeze_object,
)
from ...policies import IdlePolicy
from ...storage.codec import decode, encode
from ...storage.state import Claim
from .codec import COMPONENT

if TYPE_CHECKING:
    from .repository import NavigationRepository


class CanonicalHost(Protocol):
    async def canonical_component_read(
        self,
        key: IdleConversationKey,
        *,
        component: str,
        operation_id: str = "",
        token: str = "",
        reservation_id: str = "",
        index_keys: tuple[str, ...] = (),
    ) -> Mapping[str, object]: ...
    async def canonical_component_transaction(
        self,
        key: IdleConversationKey,
        *,
        component: str,
        expected_version: int | None,
        record: RuntimeSnapshot,
        ledger_delta: Mapping[str, object],
        policy: IdlePolicy | None = None,
        coordination_scope: object | None = None,
        expected_manifest: str | None = None,
        allow_idle_operation_id: str | None = None,
        expires_at: float | None = None,
        claim: Claim | None = None,
        finalize_idle_operation_id: str | None = None,
    ) -> RuntimeSnapshot: ...


async def read(
    repo: NavigationRepository,
    key: ConversationKey,
    *,
    operation_id: str = "",
    token: str = "",
    reservation_id: str = "",
    index_keys: tuple[str, ...] = (),
    view_id: str = "",
    session_id: str | None = None,
) -> NavigationLedgerReducer:
    if view_id and session_id is not None:
        index_keys = (*index_keys, NavigationLedgerReducer.view_index(view_id, session_id))
    payload = await cast(CanonicalHost, repo.idle.backend).canonical_component_read(
        repo.mapping.to_idle(key),
        component=COMPONENT,
        operation_id=operation_id,
        token=token,
        reservation_id=reservation_id,
        index_keys=index_keys,
    )
    reducer = NavigationLedgerReducer(
        key,
        LedgerRead.from_payload(payload),
        clock=repo.clock,
        config=repo.config,
        required_indexes=index_keys,
    )
    if view_id and session_id is None and reducer.session_id is not None:
        required = (*index_keys, NavigationLedgerReducer.view_index(view_id, reducer.session_id))
        second = await read(
            repo,
            key,
            operation_id=operation_id,
            token=token,
            reservation_id=reservation_id,
            index_keys=required,
        )
        if second.session_id != reducer.session_id:
            from aiogram_nav.errors import VersionConflict

            raise VersionConflict("Navigation session changed during view ownership observation")
        return second
    return reducer


def value(
    repo: NavigationRepository, key: ConversationKey, reducer: NavigationLedgerReducer
) -> JsonObject:
    delta = reducer.delta()
    return freeze_object(
        {
            "schema": 3,
            "profile": repo.profile,
            "canonical": True,
            "revision": delta.revision,
            "hot": delta.hot,
            "identity": navigation_identity(key),
        },
        max_bytes=8_388_608,
    )


async def accepted_activity(
    repo: NavigationRepository, key: ConversationKey, operation_id: str
) -> ActivitySnapshot:
    reducer = await read(repo, key, operation_id=operation_id)
    payload = reducer.integration_payload(operation_id)
    if not isinstance(payload, str):
        from ...errors import SchemaUnsupported

        raise SchemaUnsupported("Canonical operation has no accepted activity result")
    activity = decode(payload)
    if not isinstance(activity, ActivitySnapshot):
        from ...errors import SchemaUnsupported

        raise SchemaUnsupported("Canonical activity replay result is malformed")
    return activity


def save_activity(
    reducer: NavigationLedgerReducer, operation_id: str, activity: ActivitySnapshot
) -> None:
    reducer.set_integration_payload(operation_id, encode(activity, schema_version=3))
