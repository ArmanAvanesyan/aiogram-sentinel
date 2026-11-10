"""Opt-in combined ownership, policies and dispatcher wiring."""

from __future__ import annotations

# Runtime installation has to validate stopped lifecycle and exact writer identity.
# pyright: reportPrivateUsage=false
from collections.abc import Mapping
from typing import TYPE_CHECKING

from aiogram import Dispatcher, Router
from aiogram_coordination import BorrowedFsmCoordinator
from aiogram_nav.config import NavigationConfig
from aiogram_nav.errors import ConfigurationError as NavigationConfigurationError
from aiogram_nav.navigation import Navigation
from aiogram_nav.registry import NavigationRegistry
from aiogram_nav.rendering.base import CleanupRequest

from ...coordinator import AiogramMemoryCoordinator, MemoryCoordinator
from ...errors import ConfigurationError, OwnershipLost
from ...models import ActionReceipt, ActivityGuard, ActivitySnapshot, RuntimeSnapshot
from ...protocols import FlowAdapter
from ...runtime import IdleRuntime
from ...storage.redis_coordinator import RedisCoordinator
from .adapters import NavigationFlowAdapter
from .codec import COMPONENT, load_ledger
from .mapping import IdentityMapping, MappedCoordinator
from .policies import NodePolicies
from .presentation import NavigationPresentation
from .repository import NavigationRepository

if TYPE_CHECKING:
    from aiogram_nav.models import ConversationKey


class NavigationIntegration:
    """Own the one navigation writer and the idle activity mapped to it.

    Optional application adapters supply eligibility and business cancellation;
    screen reconstruction belongs to navigation. Install this integration once,
    before polling, instead of installing either standalone middleware.
    """

    def __init__(
        self,
        *,
        idle: IdleRuntime,
        registry: NavigationRegistry,
        policies: NodePolicies,
        adapters: Mapping[str, FlowAdapter] | None = None,
        identity_mapping: IdentityMapping | None = None,
        config: NavigationConfig | None = None,
    ) -> None:
        if idle._task is not None or idle._installed or idle.coordinator.active_scopes:
            raise ConfigurationError(
                "Construct navigation integration before starting/installing idle"
            )
        if (
            idle.component_finalizer is not None
            or idle.component_recovery is not None
            or idle.component_after_commit is not None
            or idle.component_validator is not None
            or "aiogram_nav" in idle.adapters
        ):
            raise ConfigurationError(
                "Idle runtime already has an integration writer or reserved adapter"
            )
        self.idle, self.registry, self.policies = idle, registry, policies
        self.adapters = dict(adapters or {})
        for node in self.adapters:
            registry.get(node)
        policies.validate(registry, idle.policies)
        try:
            self.navigation_repository = NavigationRepository(
                idle=idle,
                registry=registry,
                policies=policies,
                config=config,
                identity_mapping=identity_mapping,
            )
        except NavigationConfigurationError as error:
            raise ConfigurationError(str(error)) from error
        self.navigation: Navigation | None = None
        self._installed = False
        self._flow_adapter = NavigationFlowAdapter(self)
        idle.adapters["aiogram_nav"] = self._flow_adapter
        idle.component_finalizer = self.navigation_repository.finalize
        idle.component_recovery = self.navigation_repository.recover_component
        idle.component_after_commit = self.after_commit
        idle.component_validator = self.validate

    def validate(self) -> None:
        """Reject changed writer hooks before accepting or executing work."""
        idle, repository = self.idle, self.navigation_repository
        if not isinstance(idle.coordinator, BorrowedFsmCoordinator) and type(
            idle.coordinator
        ) not in {
            MemoryCoordinator,
            AiogramMemoryCoordinator,
            RedisCoordinator,
        }:
            raise ConfigurationError("Unsupported integrated coordinator implementation")
        if (
            idle.adapters.get(repository.adapter_key) is not self._flow_adapter
            or idle.component_finalizer != repository.finalize
            or idle.component_recovery != repository.recover_component
            or idle.component_after_commit != self.after_commit
            or idle.component_validator != self.validate
        ):
            raise ConfigurationError("The integrated component writer hooks changed")
        coordinator = repository.coordinator
        if (
            not isinstance(coordinator, MappedCoordinator)
            or coordinator.underlying is not idle.coordinator
            or coordinator.mapping is not repository.mapping
        ):
            raise ConfigurationError("Integrated navigation no longer shares idle coordination")
        navigation = self.navigation
        if navigation is not None and (
            navigation.repository is not repository
            or navigation.registry is not self.registry
            or navigation.coordinator is not coordinator
            or repository.navigation is not navigation
            or navigation.namespace != idle.namespace
            or navigation.session_validator != repository.authorize_session
            or navigation.session_authority is not None
        ):
            raise ConfigurationError("The bound navigation writer configuration changed")

    def bind(self, navigation: Navigation) -> None:
        self.validate()
        if self.idle._task is not None and self.navigation is not navigation:
            raise ConfigurationError("Bind integrated navigation before starting idle workers")
        if (
            navigation.repository is not self.navigation_repository
            or navigation.registry is not self.registry
        ):
            raise ConfigurationError("Integration requires its own repository and registry")
        if navigation.namespace != self.idle.namespace:
            raise ConfigurationError("Idle and navigation namespaces must match losslessly")
        if self.navigation is not None and self.navigation is not navigation:
            raise ConfigurationError("Only one Navigation writer may bind this integration")
        if (
            self.navigation_repository.navigation is not None
            and self.navigation_repository.navigation is not navigation
        ):
            raise ConfigurationError("The projection already has a different navigation writer")
        if (
            self.idle.bot is not None
            and navigation.bot is not None
            and self.idle.bot.id != navigation.bot.id
        ):
            raise ConfigurationError("Idle and navigation bots differ")
        if (
            navigation.session_authority is not None
            and navigation.session_authority is not self.idle.session_authority
        ):
            raise ConfigurationError("Combined runtimes require one SessionAuthority instance")
        if navigation.session_validator not in {None, self.navigation_repository.authorize_session}:
            raise ConfigurationError("Combined session validation has another owner")
        if self.idle.bot is None:
            self.idle.bot = navigation.bot
        elif navigation.bot is None:
            navigation.bot = self.idle.bot
        if not isinstance(navigation.presenter, NavigationPresentation):
            navigation.presenter = NavigationPresentation(self, navigation.presenter)
        elif navigation.presenter.integration is not self:
            raise ConfigurationError("Navigation presenter belongs to another integration")
        navigation.session_authority = None
        navigation.session_validator = self.navigation_repository.authorize_session
        self.navigation = navigation
        self.navigation_repository.bind_navigation(navigation)

    def install(
        self,
        dispatcher: Dispatcher,
        *,
        navigation: Navigation,
        lifecycle: bool = True,
        bindings_mode: str = "automatic",
        bindings_router: Router | None = None,
        allow_root_handlers: bool = False,
    ) -> None:
        if self._installed:
            raise ConfigurationError("Navigation integration is already installed")
        from .installation import install, validate_install

        validate_install(
            self,
            dispatcher,
            navigation,
            bindings_mode=bindings_mode,
            bindings_router=bindings_router,
            allow_root_handlers=allow_root_handlers,
        )
        previous = (
            self.navigation,
            self.navigation_repository.navigation,
            navigation.presenter,
            navigation.bot,
            self.idle.bot,
            navigation.session_authority,
            navigation.session_validator,
        )
        try:
            self.bind(navigation)
            install(
                self,
                dispatcher,
                navigation,
                lifecycle=lifecycle,
                bindings_mode=bindings_mode,
                bindings_router=bindings_router,
                allow_root_handlers=allow_root_handlers,
            )
        except ConfigurationError:
            (
                self.navigation,
                self.navigation_repository.navigation,
                navigation.presenter,
                navigation.bot,
                self.idle.bot,
                navigation.session_authority,
                navigation.session_validator,
            ) = previous
            raise
        self._installed = True

    def application_adapter(self, node_id: str) -> FlowAdapter | None:
        for node in self.registry.ancestors(node_id):
            if node.id in self.adapters:
                return self.adapters[node.id]
        return None

    async def touch(
        self, key: ConversationKey, *, operation_id: str, expected: ActivityGuard
    ) -> ActivitySnapshot:
        return await self.navigation_repository.integration_touch(
            key, operation_id=operation_id, expected=expected
        )

    async def restart_activity(
        self, key: ConversationKey, *, operation_id: str, expected: ActivityGuard
    ) -> ActivitySnapshot:
        """Explicit same-screen restart allocates a fresh idle activity generation."""
        return await self.navigation_repository.integration_touch(
            key, operation_id=operation_id, expected=expected, restart=True
        )

    async def after_commit(
        self, old: RuntimeSnapshot, committed: RuntimeSnapshot, receipt: ActionReceipt
    ) -> None:
        """Best-effort tracked UI cleanup, after the one atomic lifecycle commit."""
        nav = self.navigation
        if nav is None or COMPONENT not in receipt.component_updates:
            return
        key = self.navigation_repository.mapping.to_nav(committed.key)
        before = load_ledger(old, key, expected_profile=self.navigation_repository.profile)
        after = load_ledger(committed, key, expected_profile=self.navigation_repository.profile)
        if before is None or before.current is None or after is None or after.current is None:
            return
        scope = self.idle.coordinator.scope_token(committed.key)
        if scope is None:
            return
        latest = await self.navigation_repository.load(key)
        expected = after.current.snapshot
        if latest is None or (latest.snapshot.session_id, latest.snapshot.view.view_id) != (
            expected.session_id,
            expected.view.view_id,
        ):
            return

        def ensure_owned() -> None:
            if not self.idle.coordinator.scope_matches(committed.key, scope):
                raise OwnershipLost("Integrated cleanup coordination scope expired")

        ensure_owned()
        await nav.presenter.cleanup(
            CleanupRequest(
                key,
                before.current.snapshot.view,
                expected.view,
                nav.bot,
                ensure_owned,
            )
        )
