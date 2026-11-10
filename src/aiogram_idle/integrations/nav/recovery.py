"""Recover known operations; park opaque unsupported components without decoding."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from aiogram_nav.errors import (
    AccessDenied,
    ConfigurationError,
    InvalidParameters,
    RenderUnknown,
    SchemaUnsupported,
    SessionExpired,
)

from ...models import IdleConversationKey, RuntimeSnapshot, freeze_object
from ...storage.state import Claim
from .codec import COMPONENT, OWNER
from .engine import STAGING_CLAIM, ComponentBackend

if TYPE_CHECKING:
    from .repository import NavigationRepository


async def park(
    repo: NavigationRepository,
    key: IdleConversationKey,
    *,
    reason: str,
    operation_id: str,
    claim: Claim | None,
) -> None:
    """Change generic recovery metadata, preserving the opaque payload verbatim."""
    latest = await repo.idle.backend.load(key)
    if latest is None:
        raise ConfigurationError("The component recovery record disappeared")
    value = latest.components.get(OWNER)
    if (
        not isinstance(value, Mapping)
        or value.get("component") != COMPONENT
        or value.get("pending") is not True
    ):
        raise ConfigurationError("Cannot park an unowned component recovery slot")
    marker: dict[str, object] = dict(cast(Mapping[str, object], value))
    marker.update(parked=True, failure_reason=reason)
    changed = replace(
        latest, components=freeze_object({**latest.components, OWNER: marker}, max_bytes=8_388_608)
    )
    digest = hashlib.sha256(f"park:{latest.version}:{operation_id}:{reason}".encode()).hexdigest()
    nav_key = repo.mapping.to_nav(key)
    await cast(ComponentBackend, repo.idle.backend).component_transaction(
        key,
        component=COMPONENT,
        expected_version=latest.version,
        operation_id="nav:park:" + digest,
        fingerprint=digest,
        record=changed,
        coordination_scope=repo.coordinator.scope_token(nav_key),
        claim=claim,
    )


async def recover(repo: NavigationRepository, record: RuntimeSnapshot, claim: object) -> bool:
    if record.idle.operation is not None:
        return False
    key = repo.mapping.to_nav(record.key)
    owned_claim = claim if isinstance(claim, Claim) else None
    try:
        pending = await repo.pending(key)
    except SchemaUnsupported:
        await park(
            repo,
            record.key,
            reason="SchemaUnsupported",
            operation_id="opaque-component",
            claim=owned_claim,
        )
        return True
    if pending is None:
        owner = record.components.get(OWNER)
        if (
            isinstance(owner, Mapping)
            and owner.get("component") == COMPONENT
            and owner.get("pending") is True
        ):
            await park(
                repo,
                record.key,
                reason="MissingPendingOperation",
                operation_id="opaque-component",
                claim=owned_claim,
            )
            return True
        return False
    if repo.navigation is None:
        raise ConfigurationError("Bind navigation before running integrated recovery")
    claim_marker = STAGING_CLAIM.set(owned_claim)
    try:
        await repo.navigation.recover(key, operation_id=pending.operation_id)
    except (
        RenderUnknown,
        SessionExpired,
        AccessDenied,
        InvalidParameters,
        SchemaUnsupported,
    ) as error:
        await park(
            repo,
            record.key,
            reason=type(error).__name__,
            operation_id=pending.operation_id,
            claim=owned_claim,
        )
    finally:
        STAGING_CLAIM.reset(claim_marker)
    return True
