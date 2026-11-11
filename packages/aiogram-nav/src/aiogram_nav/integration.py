"""Full-handler isolation and an explicit router for requested navigation inputs."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import DisabledEventIsolation, SimpleEventIsolation
from aiogram.fsm.strategy import FSMStrategy
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from aiogram_coordination import BorrowedFsmCoordinator, TrackedEventIsolation

from .errors import ConfigurationError, StaleView, UnsupportedContext
from .fsm_validation import validate_fsm_storage as _validate_fsm_storage
from .identity import private_identity
from .inputs.bindings import (
    CallbackEntry,
    InputBindings,
    MatchedEntry,
    Translator,
)
from .inputs.callbacks import acknowledge as _ack
from .inputs.tokens import parse_callback_data
from .isolation import AiogramMemoryCoordinator, MemoryCoordinator
from .models import NavigationAction

if TYPE_CHECKING:
    from .context import NavigationContext
    from .navigation import Navigation

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class NavigationMiddleware(BaseMiddleware):
    def __init__(
        self,
        navigation: Navigation,
        dispatcher: Dispatcher,
        *,
        manual: bool = False,
        allow_root_handlers: bool = False,
    ) -> None:
        self.navigation = navigation
        self.manual = manual
        self.allow_root_handlers = allow_root_handlers
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
        if (
            not self.manual
            and self.bindings_router is not None
            and (
                not dispatcher.sub_routers
                or dispatcher.sub_routers[0] is not self.bindings_router
                or self.bindings_router.parent_router is not dispatcher
            )
        ):
            raise ConfigurationError("Navigation bindings must precede business routers")
        if isinstance(self.coordinator, BorrowedFsmCoordinator) and (
            self.coordinator.fsm_isolation
            is not (
                self.isolation
                if isinstance(self.isolation, (SimpleEventIsolation, TrackedEventIsolation))
                else None
            )
        ):
            raise ConfigurationError(
                "The coordinator must keep the verified FSM isolation instance"
            )
        middlewares = list(dispatcher.update.outer_middleware)
        enabled = dispatcher.fsm in middlewares
        if enabled != self.fsm_enabled or (
            enabled and middlewares.index(dispatcher.fsm) > middlewares.index(self)
        ):
            raise ConfigurationError("Navigation must run after the original FSM middleware")
        if (
            not self.allow_root_handlers
            and self.navigation.bindings
            and (dispatcher.message.handlers or dispatcher.callback_query.handlers)
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
                await nav.reject_callback(event.event, bot, "unsupported")
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
        if self.fsm_enabled and isinstance(
            self.isolation, (SimpleEventIsolation, TrackedEventIsolation)
        ):
            if not isinstance(state, FSMContext) or not isinstance(
                coordinator, BorrowedFsmCoordinator
            ):
                raise ConfigurationError(
                    "The held FSM lock requires its verified coordinator and FSM context"
                )
            if coordinator.fsm_isolation is not self.isolation:
                raise ConfigurationError("Coordinator and Dispatcher isolation differ")
            if isinstance(self.isolation, TrackedEventIsolation) and not self.isolation.owns(
                state.key
            ):
                raise ConfigurationError("The application FSM scope is not owned by this task")
            scope = coordinator.borrowed_fsm(key)
        else:
            scope = coordinator.hold(key)
        async with scope:
            if isinstance(state, FSMContext):
                data["raw_state"] = await state.get_state()
            if nav.draining:
                raise ConfigurationError("Navigation is draining")
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
                    await nav.reject_callback(event.event, bot, "busy")
                return None
            reserved = isinstance(payload, CallbackQuery) and (payload.data or "").startswith(
                "nav:"
            )
            if self.manual and reserved and isinstance(payload, CallbackQuery):
                if not await callback_is_current(nav, payload, context):
                    await nav.reject_callback(payload, bot, "stale")
                    return None
            result = await handler(event, data)
            if self.manual and reserved and not context.control_handled:
                logger.warning("Reserved navigation callback was not handled in manual routing")
            return result


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


async def callback_is_current(
    navigation: Navigation, callback: CallbackQuery, context: NavigationContext
) -> bool:
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
        return False
    if navigation.bindings is None:
        return False
    try:
        _callback_entry(navigation.bindings, token.action, token.entry_id, current.node_id)
    except StaleView:
        return False
    return True


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
        await navigation.reject_callback(callback, bot, "stale")
        return
    bindings = navigation.bindings
    if bindings is None:
        raise ConfigurationError("Callback bindings were not installed")
    try:
        _callback_entry(bindings, token.action, token.entry_id, current.node_id)
    except StaleView:
        await navigation.reject_callback(callback, bot, "stale")
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


def install(
    navigation: Navigation,
    dispatcher: Dispatcher,
    *,
    bindings_mode: str = "automatic",
    bindings_router: Router | None = None,
    allow_root_handlers: bool = False,
) -> None:
    from .bindings_router import create_bindings_router

    if dispatcher.get("_aiogram_nav_installed") or navigation.installed:
        raise ConfigurationError("Navigation is already installed")
    if bindings_mode not in {"automatic", "manual"} or type(allow_root_handlers) is not bool:
        raise ConfigurationError("Invalid navigation routing configuration")
    manual = bindings_mode == "manual"
    if not manual and (bindings_router is not None or allow_root_handlers):
        raise ConfigurationError("Custom router/root handlers require explicit manual mode")
    if navigation.bindings is not None:
        navigation.bindings.validate(navigation.registry)
        if not allow_root_handlers and (
            dispatcher.message.handlers or dispatcher.callback_query.handlers
        ):
            raise ConfigurationError(
                "Use business Routers after navigation bindings, not Dispatcher root handlers"
            )
        if manual:
            if bindings_router is None or bindings_router is not navigation.bindings_router:
                raise ConfigurationError("Use create_bindings_router for this Navigation instance")
            parent: Router | None = bindings_router
            while parent is not None and parent is not dispatcher:
                parent = parent.parent_router
            if parent is None:
                raise ConfigurationError("Include the bindings router before manual installation")
    elif bindings_router is not None:
        raise ConfigurationError("Bindings router requires configured bindings")
    if dispatcher.fsm.strategy != FSMStrategy.USER_IN_CHAT:
        raise ConfigurationError("Navigation requires FSMStrategy.USER_IN_CHAT")
    _validate_fsm_storage(dispatcher)
    isolation = dispatcher.fsm.events_isolation
    if isinstance(isolation, (SimpleEventIsolation, TrackedEventIsolation)):
        current = navigation.coordinator
        if isinstance(current, BorrowedFsmCoordinator):
            current.configure_fsm_isolation(isolation)
            if current.fsm_isolation is not isolation:
                raise ConfigurationError("Coordinator did not retain the verified FSM isolation")
        elif getattr(current, "distributed", False):
            raise ConfigurationError(
                "Distributed navigation requires its verified fenced coordinator"
            )
        elif type(current) is MemoryCoordinator and not navigation.application_coordinator_selected:
            navigation.coordinator = AiogramMemoryCoordinator(isolation)
        else:
            raise ConfigurationError(
                "Application coordinators must implement BorrowedFsmCoordinator "
                "to preserve their FSM ownership semantics"
            )
    elif type(isolation) is not DisabledEventIsolation:
        raise ConfigurationError("Only disabled or verified Simple/Tracked isolation is supported")
    if navigation.bindings is not None and not manual:
        if navigation.bindings_router is not None:
            raise ConfigurationError("An application-created router requires manual mode")
        bindings_router = create_bindings_router(navigation)
    middleware = NavigationMiddleware(
        navigation, dispatcher, manual=manual, allow_root_handlers=allow_root_handlers
    )
    if bindings_router is not None and not manual:
        dispatcher.include_router(bindings_router)
        dispatcher.sub_routers.remove(bindings_router)
        dispatcher.sub_routers.insert(0, bindings_router)
    dispatcher.update.outer_middleware(middleware)
    middleware.bindings_router = bindings_router
    dispatcher["_aiogram_nav_installed"] = True


def _bind_bot(navigation: Navigation, bot: Bot) -> None:
    if navigation.bot is not None and navigation.bot.id != bot.id:
        raise ConfigurationError("Use one Navigation instance per Bot")
    presenter_bot = getattr(navigation.presenter, "bot", None)
    if isinstance(presenter_bot, Bot) and presenter_bot.id != bot.id:
        raise ConfigurationError("Presenter and dispatcher Bot identities differ")
    navigation.bot = bot


bind_bot = _bind_bot
is_navigation_input = _is_navigation_input
validate_fsm_storage = _validate_fsm_storage
