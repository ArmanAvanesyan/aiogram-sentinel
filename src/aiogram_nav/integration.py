"""Full-handler isolation and an explicit router for requested navigation inputs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import KeyBuilder, StorageKey
from aiogram.fsm.storage.memory import DisabledEventIsolation, SimpleEventIsolation
from aiogram.fsm.strategy import FSMStrategy
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from .errors import ConfigurationError, StaleView, UnsupportedContext
from .identity import private_identity
from .inputs.bindings import (
    CallbackEntry,
    CommandEntry,
    InputBindings,
    MatchedEntry,
    ReplyEntry,
    Translator,
)
from .inputs.callbacks import acknowledge as _ack
from .inputs.callbacks import stale as _stale
from .inputs.tokens import parse_callback_data
from .isolation import AiogramMemoryCoordinator
from .models import NavigationAction
from .storage.redis_coordinator import RedisCoordinator

if TYPE_CHECKING:
    from .context import NavigationContext
    from .navigation import Navigation

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class NavigationMiddleware(BaseMiddleware):
    def __init__(self, navigation: Navigation, dispatcher: Dispatcher) -> None:
        self.navigation = navigation
        self.dispatcher = dispatcher
        self.isolation = dispatcher.fsm.events_isolation
        self.storage = dispatcher.storage
        self.storage_signature = _validate_fsm_storage(dispatcher)
        self.coordinator = navigation.coordinator
        self.bindings_router: Router | None = None
        self.fsm_enabled = any(
            item is dispatcher.fsm for item in dispatcher.update.outer_middleware
        )

    def validate(self) -> None:
        dispatcher = self.dispatcher
        if (
            dispatcher.fsm.events_isolation is not self.isolation
            or dispatcher.fsm.strategy != FSMStrategy.USER_IN_CHAT
        ):
            raise ConfigurationError(
                "FSM isolation and strategy must remain unchanged after installation"
            )
        if (
            dispatcher.storage is not self.storage
            or _validate_fsm_storage(dispatcher) != self.storage_signature
            or self.navigation.coordinator is not self.coordinator
        ):
            raise ConfigurationError(
                "FSM storage, key mapping and navigation coordinator must remain unchanged"
            )
        if self.bindings_router is not None and (
            not dispatcher.sub_routers
            or dispatcher.sub_routers[0] is not self.bindings_router
            or self.bindings_router.parent_router is not dispatcher
        ):
            raise ConfigurationError("Navigation bindings must precede business routers")
        if (
            isinstance(self.coordinator, AiogramMemoryCoordinator)
            and self.coordinator.isolation is not self.isolation
        ):
            raise ConfigurationError(
                "The coordinator must keep the verified FSM isolation instance"
            )
        if isinstance(self.coordinator, RedisCoordinator) and (
            self.coordinator.fsm_isolation
            is not (self.isolation if type(self.isolation) is SimpleEventIsolation else None)
        ):
            raise ConfigurationError("Distributed coordinator FSM isolation changed")
        middlewares = list(dispatcher.update.outer_middleware)
        enabled = dispatcher.fsm in middlewares
        if enabled != self.fsm_enabled or (
            enabled and middlewares.index(dispatcher.fsm) > middlewares.index(self)
        ):
            raise ConfigurationError("Navigation must run after the original FSM middleware")
        if self.navigation.bindings and (
            dispatcher.message.handlers or dispatcher.callback_query.handlers
        ):
            raise ConfigurationError(
                "Include business Routers after navigation; Dispatcher root handlers outrank bindings"
            )

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)
        self.validate()
        bot = data.get("bot")
        if not isinstance(bot, Bot):
            raise ConfigurationError("Dispatcher did not supply a Bot")
        nav = self.navigation
        resolver = nav.identity or private_identity
        try:
            key = await resolver(event, bot, nav.namespace)
        except UnsupportedContext:
            if isinstance(event.event, CallbackQuery) and (event.event.data or "").startswith(
                "nav:"
            ):
                await _ack(bot, event.event.id, "This screen is no longer active.")
                return None
            raise
        if key is None:
            return await handler(event, data)
        if key.bot_id != bot.id or key.namespace != nav.namespace:
            raise UnsupportedContext(
                "Resolved navigation identity differs from the configured Bot/namespace"
            )
        payload = event.event
        if isinstance(payload, (Message, CallbackQuery)):
            actor = payload.from_user
            message = payload.message if isinstance(payload, CallbackQuery) else payload
            if (
                actor is None
                or message is None
                or key.user_id != actor.id
                or key.chat_id != message.chat.id
            ):
                raise UnsupportedContext(
                    "Resolved identity must preserve the actual actor and conversation"
                )
        _bind_bot(nav, bot)
        coordinator = nav.coordinator
        state = data.get("state")
        if isinstance(state, FSMContext):
            expected = StorageKey(bot_id=key.bot_id, chat_id=key.chat_id, user_id=key.user_id)
            if (
                state.key != expected
                or state.storage is not self.storage
                or key.tenant_id is not None
            ):
                raise ConfigurationError(
                    "FSM and navigation identities require a lossless shared mapping"
                )
        if (
            self.fsm_enabled
            and isinstance(coordinator, (AiogramMemoryCoordinator, RedisCoordinator))
            and type(self.isolation) is SimpleEventIsolation
            and not isinstance(state, FSMContext)
        ):
            raise ConfigurationError("The held FSM lock requires its original FSM context")
        borrowed = (
            self.fsm_enabled
            and isinstance(state, FSMContext)
            and isinstance(coordinator, AiogramMemoryCoordinator)
            and coordinator.isolation is self.isolation
        )
        if borrowed and isinstance(coordinator, AiogramMemoryCoordinator):
            scope = coordinator.borrowed(key)
        elif (
            self.fsm_enabled
            and isinstance(state, FSMContext)
            and isinstance(coordinator, RedisCoordinator)
            and coordinator.fsm_isolation is self.isolation
            and type(self.isolation) is SimpleEventIsolation
        ):
            scope = coordinator.borrowed_fsm(key)
        else:
            scope = coordinator.hold(key)
        async with scope:
            if isinstance(state, FSMContext):
                data["raw_state"] = await state.get_state()
            context = nav.for_conversation(key, operation_prefix=f"update:{event.update_id}")
            data["nav_context"] = context
            data["navigation_context"] = context
            data["nav_key"] = key
            # Only explicit navigation inputs may recover a pending render. Ordinary
            # handlers must not overwrite its business state while it is unresolved.
            if await nav.is_busy(key) and not await _is_navigation_input(
                nav, event.event, context, bot
            ):
                if isinstance(event.event, CallbackQuery):
                    await _ack(bot, event.event.id, "Navigation is still being recovered.")
                return None
            return await handler(event, data)


async def _match(
    navigation: Navigation, message: Message, context: NavigationContext, bot: Bot
) -> MatchedEntry | None:
    bindings = navigation.bindings
    if bindings is None:
        return None
    current = await context.current()
    node_id = current.node_id if current else None
    command = await bindings.match_command(message, bot, node_id, global_only=True)
    if command is not None:
        return command
    command = await bindings.match_command(message, bot, node_id, global_only=False)
    if command is not None:
        return command
    locale = await navigation.locale(context.key)
    installed = (
        (current.view.reply_keyboard_locale or current.view.locale)
        if current and current.view.reply_keyboard_key is not None
        else None
    )
    allow_scoped = True
    if current:
        node = navigation.registry.resolve(current.node_id)
        allow_scoped = node.metadata.get("reply_navigation", True) is not False
    return bindings.match_reply(
        message.text or "",
        node_id,
        current_locale=locale,
        installed_locale=installed,
        translator=navigation.translator,
        allow_scoped=allow_scoped,
    )


async def _is_navigation_input(
    navigation: Navigation, event: TelegramObject, context: NavigationContext, bot: Bot
) -> bool:
    if isinstance(event, CallbackQuery):
        return bool(
            event.data
            and event.data.startswith("nav:")
            and navigation.bindings is not None
            and any(isinstance(entry, CallbackEntry) for entry in navigation.bindings.entries)
        )
    return isinstance(event, Message) and await _match(navigation, event, context, bot) is not None


class EntryFilter(BaseFilter):
    def __init__(self, navigation: Navigation) -> None:
        self.navigation = navigation

    async def __call__(
        self, message: Message, bot: Bot, nav_context: NavigationContext | None = None
    ) -> bool | dict[str, MatchedEntry]:
        if nav_context is None:
            return False
        match = await _match(self.navigation, message, nav_context, bot)
        return {"nav_match": match} if match is not None else False


class CallbackFilter(BaseFilter):
    async def __call__(
        self, callback: CallbackQuery, nav_context: NavigationContext | None = None
    ) -> bool:
        return nav_context is not None and bool(callback.data and callback.data.startswith("nav:"))


async def dispatch_action(
    context: NavigationContext, action: NavigationAction, *, source: str, operation_id: str
) -> None:
    if action.kind == "go":
        if action.target is None:
            raise ConfigurationError("Go requires a target")
        await context.go(
            action.target, params=action.params, source=source, operation_id=operation_id
        )
    elif action.kind == "home":
        await context.home(root=action.target, operation_id=operation_id, source=source)
    elif action.kind == "back":
        await context.back(operation_id=operation_id, source=source)
    elif action.kind == "cancel":
        await context.cancel(operation_id=operation_id, source=source)
    elif action.kind == "refresh":
        await context.refresh(operation_id=operation_id, source=source)
    else:
        raise ConfigurationError("This action cannot be bound to a user control")


def _callback_entry(
    bindings: InputBindings,
    token_action: NavigationAction,
    entry_id: str | None,
    node_id: str | None,
) -> CallbackEntry:
    entries = [
        entry
        for entry in bindings.entries
        if isinstance(entry, CallbackEntry)
        and entry.kind == token_action.kind
        and entry.target == token_action.target
        and (entry_id is None or entry.id == entry_id)
    ]
    if len(entries) != 1 or (entries[0].from_nodes and node_id not in entries[0].from_nodes):
        raise StaleView("Callback entry is not valid in the current scope")
    return entries[0]


async def handle_callback(
    navigation: Navigation,
    callback: CallbackQuery,
    context: NavigationContext,
    bot: Bot,
    update_id: int,
) -> None:
    raw = parse_callback_data(callback.data or "")
    token = await navigation.repository.resolve_token(context.key, raw) if raw is not None else None
    current = await context.current()
    if (
        token is None
        or current is None
        or callback.from_user.id != context.key.user_id
        or callback.message is None
        or not any(ref.message_id == callback.message.message_id for ref in current.view.messages)
    ):
        await _stale(bot, callback)
        return
    bindings = navigation.bindings
    if bindings is None:
        raise ConfigurationError("Callback bindings were not installed")
    try:
        _callback_entry(bindings, token.action, token.entry_id, current.node_id)
    except StaleView:
        await _stale(bot, callback)
        return
    await _ack(bot, callback.id)
    operation_id = "callback:" + sha256((raw or "").encode()).hexdigest()
    try:
        action = await navigation.repository.consume_token(
            context.key, raw or "", actor_id=callback.from_user.id, operation_id=operation_id
        )
    except StaleView:
        return
    await dispatch_action(context, action.action, source="inline", operation_id=operation_id)


def bind(
    navigation: Navigation, bindings: InputBindings, *, translator: Translator | None = None
) -> None:
    if getattr(navigation, "_installed", False):
        raise ConfigurationError("Configure bindings before installing navigation")
    bindings.validate(navigation.registry)
    navigation.bindings = bindings
    if translator is not None:
        navigation.translator = translator


def install(navigation: Navigation, dispatcher: Dispatcher) -> None:
    if dispatcher.get("_aiogram_nav_installed") or getattr(navigation, "_installed", False):
        raise ConfigurationError("Navigation is already installed")
    bindings = navigation.bindings
    if bindings is not None:
        bindings.validate(navigation.registry)
        if dispatcher.message.handlers or dispatcher.callback_query.handlers:
            raise ConfigurationError(
                "Use business Routers after navigation bindings, not Dispatcher root handlers"
            )
    if dispatcher.fsm.strategy != FSMStrategy.USER_IN_CHAT:
        raise ConfigurationError("Navigation requires FSMStrategy.USER_IN_CHAT")
    _validate_fsm_storage(dispatcher)
    isolation = dispatcher.fsm.events_isolation
    if type(isolation) is SimpleEventIsolation and isinstance(
        navigation.coordinator, RedisCoordinator
    ):
        navigation.coordinator.configure_fsm_isolation(isolation)
    elif type(isolation) is SimpleEventIsolation:
        current = navigation.coordinator
        if getattr(current, "distributed", False):
            raise ConfigurationError("Distributed navigation requires a verified RedisCoordinator")
        if isinstance(current, AiogramMemoryCoordinator):
            if current.isolation is not isolation:
                raise ConfigurationError(
                    "Shared navigation requires the same FSM isolation instance"
                )
        else:
            navigation.coordinator = AiogramMemoryCoordinator(isolation)
    elif type(isolation) is not DisabledEventIsolation:
        raise ConfigurationError("Only disabled or verified SimpleEventIsolation is supported")
    middleware = NavigationMiddleware(navigation, dispatcher)
    dispatcher.update.outer_middleware(middleware)
    bindings = navigation.bindings
    if bindings is not None:
        if dispatcher.message.handlers or dispatcher.callback_query.handlers:
            raise ConfigurationError(
                "Use business Routers after navigation bindings, not Dispatcher root handlers"
            )
        router = Router(name="aiogram-nav")
        if any(isinstance(entry, (CommandEntry, ReplyEntry)) for entry in bindings.entries):

            async def entry_handler(
                message: Message,
                nav_context: NavigationContext,
                nav_match: MatchedEntry,
                event_update: Update,
            ) -> None:
                await dispatch_action(
                    nav_context,
                    nav_match.action,
                    source=nav_match.source,
                    operation_id=f"update:{event_update.update_id}:nav:{nav_match.entry.id}",
                )

            router.message.register(entry_handler, EntryFilter(navigation))
        if any(isinstance(entry, CallbackEntry) for entry in bindings.entries):

            async def callback_handler(
                callback: CallbackQuery,
                nav_context: NavigationContext,
                bot: Bot,
                event_update: Update,
            ) -> None:
                await handle_callback(
                    navigation, callback, nav_context, bot, event_update.update_id
                )

            router.callback_query.register(callback_handler, CallbackFilter())
        dispatcher.include_router(router)
        dispatcher.sub_routers.remove(router)
        dispatcher.sub_routers.insert(0, router)
        middleware.bindings_router = router
    dispatcher["_aiogram_nav_installed"] = True


def _bind_bot(navigation: Navigation, bot: Bot) -> None:
    if navigation.bot is not None and navigation.bot.id != bot.id:
        raise ConfigurationError("Use one Navigation instance per Bot")
    presenter_bot = getattr(navigation.presenter, "bot", None)
    if isinstance(presenter_bot, Bot) and presenter_bot.id != bot.id:
        raise ConfigurationError("Presenter and dispatcher Bot identities differ")
    navigation.bot = bot


def _validate_fsm_storage(dispatcher: Dispatcher) -> tuple[str, ...] | None:
    # A correct StorageKey does not prove the store's builder preserves it.
    # Inspect known RedisStorage structurally so core never imports Redis.
    if not any(
        cls.__module__ == "aiogram.fsm.storage.redis" and cls.__name__ == "RedisStorage"
        for cls in type(dispatcher.storage).__mro__
    ):
        return None
    builder = getattr(dispatcher.storage, "key_builder", None)
    if not isinstance(builder, KeyBuilder):
        raise ConfigurationError("Redis FSM storage requires a verified key builder")
    identities = [
        StorageKey(bot_id=1, chat_id=7, user_id=11),
        StorageKey(bot_id=2, chat_id=7, user_id=11),
        StorageKey(bot_id=1, chat_id=8, user_id=11),
        StorageKey(bot_id=1, chat_id=7, user_id=12),
    ]
    try:
        keys = [builder.build(key, field) for key in identities for field in ("state", "data")]
        valid = (
            all(isinstance(cast(object, key), str) and key for key in keys) and len(set(keys)) == 8
        )
    except Exception as error:
        raise ConfigurationError("FSM key builder cannot encode navigation identities") from error
    if not valid:
        raise ConfigurationError(
            "FSM keys must separate bot/chat/user/field; use DefaultKeyBuilder(with_bot_id=True)"
        )

    return tuple(keys)
