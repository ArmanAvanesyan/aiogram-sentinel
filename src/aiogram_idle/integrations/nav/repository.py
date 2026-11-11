"""NavigationRepository projection over an idle-owned component transaction."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, TypeVar

from aiogram_nav.clock import Clock
from aiogram_nav.config import NavigationConfig
from aiogram_nav.errors import ConfigurationError, OwnershipLost
from aiogram_nav.models import (
    ActionStatus,
    CommitResult,
    ConversationKey,
    EffectCheckpoint,
    NavigationIntent,
    NavigationMutation,
    NavigationToken,
    PreparedAction,
    RenderResult,
    VersionedSnapshot,
)
from aiogram_nav.protocols import Coordinator
from aiogram_nav.registry import NavigationRegistry
from aiogram_nav.storage.memory import MemoryNavigationRepository

from ...errors import IdleError
from ...models import (
    ActionReceipt,
    ActivityGuard,
    ActivitySnapshot,
    FlowContext,
    RuntimeSnapshot,
    fingerprint,
)
from .codec import profile
from .engine import STAGING, STAGING_CLAIM, apply, reducer
from .errors import navigation_error
from .mapping import IdentityMapping, MappedCoordinator, NavigationClock, VerifiedIdentityMapping
from .policies import NodePolicies

if TYPE_CHECKING:
    from aiogram_nav import Navigation

    from ...runtime import IdleRuntime

T = TypeVar("T")


class NavigationRepository:
    capabilities = frozenset(
        {"conditional_commits", "prepared_actions", "opaque_tokens", "integrated"}
    )

    def __init__(
        self,
        *,
        idle: IdleRuntime,
        registry: NavigationRegistry,
        policies: NodePolicies,
        config: NavigationConfig | None = None,
        identity_mapping: IdentityMapping | None = None,
        adapter_key: str = "aiogram_nav",
    ) -> None:
        if "component_transactions" not in idle.backend.capabilities:
            raise ConfigurationError("Idle backend lacks atomic opaque component transactions")
        self.idle, self.registry, self.policies = idle, registry, policies
        self.config = config or NavigationConfig()
        self.mapping = VerifiedIdentityMapping(identity_mapping or IdentityMapping())
        self.adapter_key = adapter_key
        policies.validate(registry, idle.policies)
        self.profile = profile(self.config, policies, registry)
        self.clock: Clock = NavigationClock(idle.clock)
        self.coordinator: Coordinator = MappedCoordinator(idle.coordinator, self.mapping)
        self.navigation: Navigation | None = None

    async def migrate_canonical(
        self, key: ConversationKey, *, limit: int = 32, dry_run: bool = True
    ):
        from .canonical_migration import migrate

        try:
            return await migrate(self, key, limit=limit, dry_run=dry_run)
        except IdleError as error:
            raise navigation_error(error) from error

    @property
    def atomic_adoption(self) -> bool:
        return getattr(self.idle.backend, "active_storage_format", 1) == 3

    async def adopt_render(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        rendered: RenderResult,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        return await self._apply(
            key,
            lambda memory: memory.adopt_render(
                key,
                expected_version=expected_version,
                intent=intent,
                rendered=rendered,
                coordination_scope=None,
            ),
            scope=coordination_scope,
            accepted=intent.accepted_activity,
            deadline=lambda result: 0 if result.duplicate else result.snapshot.expires_at,
            operation_id=intent.operation_id,
            view_id=intent.view_id or "",
        )

    def key_to_idle(self, key: ConversationKey):
        return self.mapping.to_idle(key)

    def bind_navigation(self, navigation: Navigation) -> None:
        if navigation.repository is not self or navigation.registry is not self.registry:
            raise ConfigurationError("Navigation must use this projection and registry")
        if self.navigation is not None and self.navigation is not navigation:
            raise ConfigurationError("A projection has only one navigation writer")
        self.navigation = navigation

    def bind_coordinator(self, coordinator: Coordinator) -> None:
        if coordinator is not self.coordinator:
            raise ConfigurationError("Integrated navigation must share idle coordination")

    async def _memory(
        self,
        key: ConversationKey,
        *,
        operation_id: str = "",
        token: str = "",
        reservation_id: str = "",
    ) -> MemoryNavigationRepository:
        try:
            await self.idle.initialize()
            if getattr(self.idle.backend, "active_storage_format", 1) == 3:
                from .canonical import read

                return (
                    await read(
                        self,
                        key,
                        operation_id=operation_id,
                        token=token,
                        reservation_id=reservation_id,
                    )
                ).repository
            return reducer(self, key, await self.idle.backend.load(self.mapping.to_idle(key)))
        except IdleError as error:
            raise navigation_error(error) from error

    async def _apply(
        self,
        key: ConversationKey,
        callback: Callable[[MemoryNavigationRepository], Awaitable[T]],
        *,
        scope: object | None = None,
        deadline: Callable[[T], int] | None = None,
        accepted: bool = False,
        restart: bool = False,
        operation_id: str = "",
        token: str = "",
        reservation_id: str = "",
        index_keys: tuple[str, ...] = (),
        view_id: str = "",
    ) -> T:
        try:
            return await apply(
                self,
                key,
                callback,
                scope=scope,
                deadline=deadline,
                accepted=accepted,
                restart=restart,
                operation_id=operation_id,
                token=token,
                reservation_id=reservation_id,
                index_keys=index_keys,
                view_id=view_id,
            )
        except IdleError as error:
            raise navigation_error(error) from error

    async def authorize_session(self, key: ConversationKey, expected_session_id: str | None = None):
        from .sessions import authorize

        return await authorize(self, key, expected_session_id)

    async def load(self, key: ConversationKey) -> VersionedSnapshot | None:
        from .overlay import visible

        try:
            await self.idle.initialize()
            record = await self.idle.backend.load(self.mapping.to_idle(key))
            if getattr(self.idle.backend, "active_storage_format", 1) == 3:
                from .codec import load_ledger
                from .sessions import authorize

                observed = await authorize(self, key)
                if observed is not None:
                    from .sessions import binding

                    source = binding(record)
                    if source is None or source.get("session_id") != observed.session_id:
                        return None
                ledger = load_ledger(record, key, expected_profile=self.profile)
                loaded = ledger.current if ledger else None
                if loaded is not None and loaded.snapshot.expires_at <= self.clock.now():
                    loaded = None
                return visible(loaded, record)
            memory = await self._memory(key)
            from .sessions import observe, seed

            await seed(self, key, record, memory, await observe(self, key))
            return visible(await memory.load(key), record)
        except IdleError as error:
            raise navigation_error(error) from error

    async def prepare(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        intent: NavigationIntent,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        return await self._apply(
            key,
            lambda memory: memory.prepare(key, expected_version=expected_version, intent=intent),
            scope=coordination_scope,
            deadline=lambda result: result.expires_at,
            operation_id=intent.operation_id,
            view_id=intent.view_id or "",
        )

    async def checkpoint(
        self,
        key: ConversationKey,
        *,
        operation_id: str,
        effect: EffectCheckpoint,
        coordination_scope: object | None = None,
    ) -> PreparedAction:
        return await self._apply(
            key,
            lambda memory: memory.checkpoint(key, operation_id=operation_id, effect=effect),
            scope=coordination_scope,
            deadline=(lambda result: result.expires_at) if effect.state == "started" else None,
            operation_id=operation_id,
        )

    async def lookup_operation(self, key: ConversationKey, *, operation_id: str) -> ActionStatus:
        return await (await self._memory(key, operation_id=operation_id)).lookup_operation(
            key, operation_id=operation_id
        )

    async def commit(
        self,
        key: ConversationKey,
        *,
        expected_version: str | None,
        mutation: NavigationMutation,
        coordination_scope: object | None = None,
    ) -> CommitResult:
        result = await self._apply(
            key,
            lambda memory: memory.commit(key, expected_version=expected_version, mutation=mutation),
            scope=coordination_scope,
            accepted=mutation.accepted_activity,
            deadline=lambda result: 0 if result.duplicate else result.snapshot.expires_at,
            operation_id=mutation.operation_id,
        )
        if mutation.kind == "touch":
            await self._recover_overlay(key, mutation.operation_id)
        return result

    async def pending(self, key: ConversationKey) -> PreparedAction | None:
        return await (await self._memory(key)).pending(key)

    async def mark_unknown(self, key: ConversationKey, *, operation_id: str) -> None:
        await self._apply(
            key,
            lambda memory: memory.mark_unknown(key, operation_id=operation_id),
            operation_id=operation_id,
        )

    async def abandon(
        self, key: ConversationKey, operation_id: str, *, expected_session_id: str
    ) -> None:
        await self._apply(
            key,
            lambda memory: memory.abandon(
                key, operation_id, expected_session_id=expected_session_id
            ),
            operation_id=operation_id,
        )

    async def reserve_token(
        self, key: ConversationKey, token: NavigationToken, *, operation_id: str
    ) -> NavigationToken:
        return await self._apply(
            key,
            lambda memory: memory.reserve_token(key, token, operation_id=operation_id),
            deadline=lambda result: result.expires_at,
            operation_id=operation_id,
            token=token.token,
            reservation_id=operation_id,
        )

    async def resolve_token(self, key: ConversationKey, token: str) -> NavigationToken | None:
        return await (await self._memory(key, token=token)).resolve_token(key, token)

    async def consume_token(
        self, key: ConversationKey, token: str, *, actor_id: int, operation_id: str
    ) -> NavigationToken:
        return await self._apply(
            key,
            lambda memory: memory.consume_token(
                key, token, actor_id=actor_id, operation_id=operation_id
            ),
            deadline=lambda result: result.expires_at,
            operation_id=operation_id,
            token=token,
            reservation_id=operation_id,
        )

    async def integration_touch(
        self,
        key: ConversationKey,
        *,
        expected: ActivityGuard,
        operation_id: str,
        restart: bool = False,
    ) -> ActivitySnapshot:
        from ...errors import ActivityConflict

        if type(restart) is not bool:
            raise ConfigurationError("Restart must be an explicit boolean")
        async with self.coordinator.hold(key):
            current = await self.idle.backend.load(self.mapping.to_idle(key))
            status = await self.lookup_operation(key, operation_id=operation_id)
            if status.status != "completed" and (
                current is None or current.activity is None or current.activity.guard != expected
            ):
                raise ActivityConflict("Mapped activity guard changed")
            loaded = await self.load(key)
            mutation = NavigationMutation(
                operation_id,
                expected.session_id,
                kind="touch",
                source="input:"
                + fingerprint(
                    {
                        "session": expected.session_id,
                        "activity": expected.activity_id,
                        "revision": expected.activity_revision,
                        "restart": restart,
                    }
                ),
            )
            await self._apply(
                key,
                lambda memory: memory.commit(
                    key, expected_version=loaded.version if loaded else None, mutation=mutation
                ),
                scope=self.coordinator.scope_token(key),
                accepted=True,
                restart=restart,
                deadline=lambda result: 0 if result.duplicate else result.snapshot.expires_at,
                operation_id=operation_id,
            )
            await self._recover_overlay(key, operation_id)
            updated = await self.idle.backend.load(self.mapping.to_idle(key))
            if updated is None or updated.activity is None:
                raise ActivityConflict("Mapped activity is unavailable")
            from .codec import COMPONENT
            from .receipts import resolve

            value = updated.components[COMPONENT]
            from collections.abc import Mapping

            if not isinstance(value, Mapping):
                raise ActivityConflict("Mapped navigation component is unavailable")
            if value.get("schema") == 3:
                from .canonical import accepted_activity

                return await accepted_activity(self, key, operation_id)
            return resolve(value, operation_id)

    async def _recover_overlay(self, key: ConversationKey, touch_id: str) -> None:
        from .overlay import operation_id

        if self.navigation is None or self.coordinator.scope_token(key) is None:
            return
        pending = await self.pending(key)
        if pending is not None and pending.operation_id == operation_id(touch_id):
            await self.navigation.recover(key, operation_id=pending.operation_id)

    async def sweep(self, *, limit: int = 100) -> int:
        return await self.idle.backend.reconcile(limit=limit)

    async def close(self) -> None:
        if self.coordinator.active_scopes:
            raise ConfigurationError("Drain shared coordination before closing navigation")
        # Integration never owns/closes the idle backend or its client.

    @asynccontextmanager
    async def staging(self, context: FlowContext):
        current = await self.idle.backend.load(context.key)
        if (
            current is None
            or current.idle.operation is None
            or current.idle.operation.operation_id != context.operation_id
        ):
            raise OwnershipLost("The idle operation no longer owns staged navigation")
        from ...storage.state import Claim

        candidate = getattr(context.effects, "claim", None)
        marker = STAGING.set(context.operation_id)
        claim_marker = STAGING_CLAIM.set(candidate if isinstance(candidate, Claim) else None)
        try:
            yield
        finally:
            STAGING_CLAIM.reset(claim_marker)
            STAGING.reset(marker)

    async def prepare_staged(
        self, context: FlowContext, target: str, *, operation_id: str
    ) -> PreparedAction:
        key = self.mapping.to_nav(context.key)
        current = await self.load(key)
        prepared = await self.prepare(
            key,
            expected_version=current.version if current else None,
            intent=NavigationIntent(
                operation_id,
                target,
                params=current.snapshot.params
                if current is not None and current.snapshot.node_id == target
                else {},
                history="none",
                source="idle",
                accepted_activity=False,
            ),
            coordination_scope=self.coordinator.scope_token(key),
        )
        if getattr(self.idle.backend, "active_storage_format", 1) == 3:
            return prepared
        if prepared.effects.get("render") is not None:
            # Reserving the navigation intent is itself a recoverable stage.
            # A lost outer receipt must not restart or downgrade that intent.
            return prepared
        return await self.checkpoint(
            key,
            operation_id=prepared.operation_id,
            effect=EffectCheckpoint("render", "started"),
            coordination_scope=self.coordinator.scope_token(key),
        )

    async def stage(
        self,
        context: FlowContext,
        prepared: PreparedAction,
        rendered: RenderResult,
        *,
        operation_id: str,
        disposition: str = "rearm",
    ) -> ActionReceipt:
        from .staging import stage

        return await stage(
            self, context, prepared, rendered, operation_id=operation_id, disposition=disposition
        )

    async def complete_canonical(
        self,
        old: RuntimeSnapshot,
        changed: RuntimeSnapshot,
        receipt: ActionReceipt,
        policy: object,
        claim: object,
    ) -> RuntimeSnapshot | None:
        from .canonical_completion import complete

        return await complete(self, old, changed, receipt, policy, claim)

    def finalize(
        self, old: RuntimeSnapshot, changed: RuntimeSnapshot, receipt: ActionReceipt
    ) -> RuntimeSnapshot:
        from .staging import finalize

        return finalize(self, old, changed, receipt)

    async def recover_component(self, record: RuntimeSnapshot, claim: object) -> bool:
        from .recovery import recover

        return await recover(self, record, claim)
