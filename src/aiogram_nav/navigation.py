"""Standalone action runtime; business drafts and FSM state remain application-owned."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import fields
from typing import TYPE_CHECKING

from aiogram import Bot

from .clock import Clock
from .config import NavigationConfig
from .context import NavigationContext
from .effects import NavigationEffects
from .errors import AccessDenied, ConfigurationError, InvalidParameters, SessionExpired
from .events import EventHook, emit
from .json import JsonObject, JsonValue, fingerprint
from .models import (
    ActionKind,
    ConversationKey,
    EffectCheckpoint,
    HistoryMode,
    NavigationEvent,
    NavigationMutation,
    NavigationSnapshot,
    Node,
    PreparedAction,
    RenderRequest,
    RenderResult,
)
from .protocols import Coordinator
from .registry import NavigationRegistry
from .rendering.base import NavigationPresenter
from .storage.base import NavigationRepository

if TYPE_CHECKING:
    from aiogram import Dispatcher

    from .identity import IdentityResolver
    from .inputs.bindings import InputBindings

Authorizer = Callable[[ConversationKey, Node, JsonObject, str], Awaitable[bool]]
LocaleResolver = Callable[[ConversationKey], Awaitable[str]]
CancelHook = Callable[[RenderRequest], Awaitable[JsonValue]]
Translator = Callable[[str, str], str]


class Navigation:
    def __init__(
        self,
        *,
        registry: NavigationRegistry,
        repository: NavigationRepository,
        presenter: NavigationPresenter,
        config: NavigationConfig | None = None,
        authorize: Authorizer | None = None,
        locale_resolver: LocaleResolver | None = None,
        cancel_hook: CancelHook | None = None,
        on_event: EventHook | None = None,
        bot: Bot | None = None,
        namespace: str = "default",
        identity: IdentityResolver | None = None,
        isolation: Coordinator | None = None,
        dependencies: Mapping[str, object] | None = None,
        bindings: InputBindings | None = None,
        translator: Translator | None = None,
    ) -> None:
        self.registry, self.repository, self.presenter = registry, repository, presenter
        self.config = config or repository.config
        for field in fields(self.config):
            if field.name != "root" and getattr(self.config, field.name) != getattr(
                repository.config, field.name
            ):
                raise ConfigurationError(
                    "Configure repository and runtime with matching storage settings"
                )
        keys = getattr(presenter, "renderer_keys", None)
        registry.validate(renderers=keys)
        if self.config.root is not None and self.config.root not in registry.roots:
            raise ConfigurationError("The configured root must belong to the registry")
        if not namespace or len(namespace) > 256:
            raise ConfigurationError("Namespace must be a bounded nonempty ID")
        self.namespace, self.identity = namespace, identity
        self.authorize, self.locale_resolver, self.cancel_hook = (
            authorize,
            locale_resolver,
            cancel_hook,
        )
        known_bot = getattr(presenter, "bot", None)
        if isinstance(known_bot, Bot) and bot is not None and known_bot.id != bot.id:
            raise ConfigurationError("Presenter and runtime bot identities differ")
        self.on_event = on_event
        self.bot = bot if bot is not None else known_bot if isinstance(known_bot, Bot) else None
        self.dependencies = dict(dependencies or {})
        self.bindings = bindings
        self.translator: Translator = translator or (lambda text_key, locale: text_key)
        self._installed = False
        if isolation is not None:
            self.coordinator = isolation

    @property
    def clock(self) -> Clock:
        return self.repository.clock

    @property
    def coordinator(self) -> Coordinator:
        return self.repository.coordinator

    @coordinator.setter
    def coordinator(self, value: Coordinator) -> None:
        self.repository.bind_coordinator(value)

    def for_conversation(
        self, key: ConversationKey, *, operation_prefix: str | None = None
    ) -> NavigationContext:
        if key.namespace != self.namespace:
            raise ConfigurationError("Conversation namespace differs from this runtime")
        if self.bot is not None and self.bot.id != key.bot_id:
            raise ConfigurationError("Conversation bot differs from this runtime")
        return NavigationContext(self, key, operation_prefix)

    async def locale(self, key: ConversationKey) -> str:
        value = await self.locale_resolver(key) if self.locale_resolver else "en"
        if not value or len(value) > 256:
            raise ConfigurationError("Locale resolver must return a bounded nonempty ID")
        return value

    async def allowed(
        self, key: ConversationKey, node: Node, params: JsonObject, source: str
    ) -> None:
        if key.namespace != self.namespace or (self.bot is not None and key.bot_id != self.bot.id):
            raise ConfigurationError("The action belongs to another runtime identity")
        if node.renderer is None:
            raise ConfigurationError("Abstract nodes cannot be navigation destinations")
        if (
            self.authorize is not None
            and await self.authorize(key, node, params, source) is not True
        ):
            raise AccessDenied("Navigation action is not authorized")

    async def pending(self, key: ConversationKey) -> PreparedAction | None:
        return await self.repository.pending(key)

    async def is_busy(self, key: ConversationKey) -> bool:
        return await self.pending(key) is not None

    async def request(
        self, prepared: PreparedAction, *, effects: NavigationEffects | None = None
    ) -> RenderRequest:
        current = await self.repository.load(prepared.key)
        node = self.registry.get(prepared.node_id)
        params = self.registry.validate_params(node.id, prepared.params)
        if fingerprint(params) != fingerprint(prepared.params):
            raise InvalidParameters("Prepared parameters cannot be reinterpreted")
        await self.allowed(prepared.key, node, params, prepared.intent.source)
        if prepared.expires_at <= self.clock.now():
            raise SessionExpired("The prepared session expired before rendering")
        return RenderRequest(
            key=prepared.key,
            operation_id=prepared.operation_id,
            node=node,
            params=params,
            view_id=prepared.view_id,
            session_id=prepared.session_id,
            current=current.snapshot if current else None,
            locale=await self.locale(prepared.key),
            bot=self.bot,
            dependencies=self.dependencies,
            effects=effects,
            expires_at=prepared.expires_at,
            delivery="send" if prepared.intent.action == "refresh" else "auto",
        )

    async def perform(
        self,
        key: ConversationKey,
        kind: ActionKind,
        *,
        operation_id: str,
        node_id: str | None = None,
        params: Mapping[str, object] | None = None,
        history: HistoryMode = "push",
        source: str = "application",
        accepted_activity: bool = True,
    ) -> RenderResult:
        from .actions import perform

        return await perform(
            self,
            key,
            kind,
            operation_id=operation_id,
            node_id=node_id,
            params=params,
            history=history,
            source=source,
            accepted_activity=accepted_activity,
        )

    async def prepare(
        self,
        key: ConversationKey,
        node_id: str,
        *,
        operation_id: str,
        params: Mapping[str, object] | None = None,
        source: str = "application",
    ) -> PreparedAction:
        from .actions import prepare

        async with self.coordinator.hold(key):
            prepared = await prepare(
                self, key, node_id, operation_id=operation_id, params=params, source=source
            )
            if prepared.status != "completed" and "render" not in prepared.effects:
                prepared = await self.repository.checkpoint(
                    key,
                    operation_id=operation_id,
                    effect=EffectCheckpoint("render", "started"),
                    coordination_scope=self.coordinator.scope_token(key),
                )
            return prepared

    async def complete(
        self, prepared: PreparedAction, *, rendered: RenderResult
    ) -> NavigationSnapshot:
        from .actions import complete

        async with self.coordinator.hold(prepared.key):
            return (await complete(self, prepared, rendered)).snapshot

    async def track(
        self,
        key: ConversationKey,
        node_id: str,
        *,
        rendered: RenderResult,
        operation_id: str,
        params: Mapping[str, object] | None = None,
        source: str = "application",
    ) -> NavigationSnapshot:
        from .actions import complete, prepare

        async with self.coordinator.hold(key):
            prepared = await prepare(
                self,
                key,
                node_id,
                operation_id=operation_id,
                params=params,
                source=source,
                kind="track",
                view_id=rendered.view_id,
            )
            if prepared.status != "completed" and "render" not in prepared.effects:
                await self.repository.checkpoint(
                    key,
                    operation_id=operation_id,
                    effect=EffectCheckpoint("render", "started"),
                    coordination_scope=self.coordinator.scope_token(key),
                )
            return (await complete(self, prepared, rendered)).snapshot

    async def touch(
        self, key: ConversationKey, *, operation_id: str, source: str = "application"
    ) -> NavigationSnapshot:
        async with self.coordinator.hold(key):
            status = await self.repository.lookup_operation(key, operation_id=operation_id)
            loaded = await self.repository.load(key)
            snapshot = (
                status.result.snapshot if status.result else loaded.snapshot if loaded else None
            )
            if snapshot is None:
                raise SessionExpired("There is no current navigation session")
            node = self.registry.get(snapshot.node_id)
            params = self.registry.validate_params(node.id, snapshot.params)
            await self.allowed(key, node, params, source)
            result = await self.repository.commit(
                key,
                expected_version=loaded.version if loaded else None,
                mutation=NavigationMutation(
                    operation_id, snapshot.session_id, kind="touch", source=source
                ),
                coordination_scope=self.coordinator.scope_token(key),
            )
            if not result.duplicate:
                await emit(
                    self.on_event,
                    NavigationEvent(
                        operation_id,
                        key,
                        snapshot.node_id,
                        result.snapshot.node_id,
                        result.snapshot.nav_revision,
                        result.snapshot.activity_revision,
                        source,
                        "touched",
                        self.clock.now(),
                    ),
                )
            return result.snapshot

    async def recover(self, key: ConversationKey, *, operation_id: str) -> RenderResult:
        from .recovery import recover

        return await recover(self, key, operation_id=operation_id)

    def bind(self, bindings: InputBindings, *, translator: Translator | None = None) -> None:
        from .integration import bind

        bind(self, bindings, translator=translator)

    def install(self, dispatcher: Dispatcher) -> None:
        from .integration import install

        if self._installed:
            raise ConfigurationError("Navigation is already installed")
        install(self, dispatcher)
        self._installed = True

    async def close(self) -> None:
        await self.repository.close()


logger = logging.getLogger(__name__)
