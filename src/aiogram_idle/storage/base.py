"""Navigation-free structural contract implemented by authoritative idle stores."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol

from ..clock import Clock
from ..config import IdleConfig
from ..models import (
    ActivityGuard,
    ActivitySnapshot,
    ConfigManifest,
    IdleConversationKey,
    RuntimeSnapshot,
    SessionGuard,
    SessionSnapshot,
)
from ..policies import IdlePolicy
from ..protocols import Coordinator
from .state import Claim, ControlToken, OperationLookup


class IdleBackend(Protocol):
    clock: Clock
    config: IdleConfig
    capabilities: frozenset[str]
    coordinator: Coordinator

    def bind_coordinator(self, coordinator: Coordinator) -> None: ...
    async def storage_format(self) -> int: ...
    async def require_storage_format(self, version: int) -> None: ...

    async def load(self, key: IdleConversationKey) -> RuntimeSnapshot | None: ...
    async def bind_external_session(
        self,
        key: IdleConversationKey,
        *,
        session_id: str,
        revision: str,
        absolute_expires_at: int,
        operation_id: str,
    ) -> SessionSnapshot: ...
    async def open_session(
        self, key: IdleConversationKey, *, lifetime_seconds: float, operation_id: str
    ) -> SessionSnapshot: ...
    async def replace_session(
        self,
        key: IdleConversationKey,
        *,
        expected: SessionGuard,
        lifetime_seconds: float,
        operation_id: str,
    ) -> SessionSnapshot: ...
    async def enter(
        self,
        key: IdleConversationKey,
        activity_key: str,
        *,
        policy_id: str,
        policy: IdlePolicy,
        adapter_key: str,
        params: Mapping[str, object],
        session_id: str,
        expires_at: float | datetime,
        operation_id: str,
        expected: ActivityGuard | None = None,
        enabled: bool = False,
        expected_manifest: str | None = None,
    ) -> ActivitySnapshot: ...
    async def touch(
        self,
        key: IdleConversationKey,
        *,
        expected: ActivityGuard,
        operation_id: str,
        enabled: bool = False,
        expected_manifest: str | None = None,
    ) -> ActivitySnapshot: ...
    async def clear(
        self, key: IdleConversationKey, *, expected: ActivityGuard, operation_id: str, reason: str
    ) -> None: ...
    async def transition(
        self,
        key: IdleConversationKey,
        *,
        expected_version: int,
        operation_id: str,
        fingerprint: str,
        transform: Callable[[RuntimeSnapshot], RuntimeSnapshot],
        claim: Claim | None = None,
        policy: IdlePolicy | None = None,
        coordination_scope: object | None = None,
    ) -> RuntimeSnapshot: ...
    async def claim_due(
        self,
        *,
        limit: int,
        lease_seconds: float,
        namespace: str | None = None,
        bot_id: int | None = None,
    ) -> list[Claim]: ...
    async def renew_claim(self, claim: Claim, *, lease_seconds: float) -> Claim: ...
    async def validate_claim(self, claim: Claim) -> None: ...
    async def release_claim(self, claim: Claim, *, retry_at: float | None = None) -> None: ...
    async def lookup_operation(
        self, key: IdleConversationKey, operation_id: str, *, not_before: float | None = None
    ) -> OperationLookup: ...
    async def reserve_control(
        self,
        key: IdleConversationKey,
        *,
        token: str,
        prompt_id: str,
        activity_id: str,
        expires_at: float,
    ) -> ControlToken: ...
    async def resolve_control(
        self, key: IdleConversationKey, token: str
    ) -> ControlToken | None: ...
    async def get_config(self) -> ConfigManifest | None: ...
    async def bootstrap_config(self, *, enabled: bool, policies_digest: str) -> ConfigManifest: ...
    async def apply_config(
        self, *, expected_generation: str, enabled: bool, policies_digest: str, operation_id: str
    ) -> ConfigManifest: ...
    async def reconcile(self, *, limit: int = 100) -> int: ...
    async def frozen_policy(self, key: IdleConversationKey) -> IdlePolicy: ...
    async def close(self) -> None: ...
