"""One optional middleware owns the shared lock and control precedence."""

from __future__ import annotations

# This adapter intentionally uses the matching, reviewed nav installation helpers.
# pyright: reportPrivateUsage=false
import logging
from typing import TYPE_CHECKING, Any, cast

from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import DisabledEventIsolation, SimpleEventIsolation
from aiogram.fsm.strategy import FSMStrategy
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from aiogram_coordination import BorrowedFsmCoordinator, TrackedEventIsolation
from aiogram_nav import create_bindings_router
from aiogram_nav.errors import UnsupportedContext as NavUnsupportedContext
from aiogram_nav.identity import private_identity
from aiogram_nav.inputs.callbacks import acknowledge as _ack
from aiogram_nav.integration import (
    Handler,
    NavigationMiddleware,
    callback_is_current,
)
from aiogram_nav.integration import (
    bind_bot as _bind_bot,
)
from aiogram_nav.integration import (
    is_navigation_input as _is_navigation_input,
)
from aiogram_nav.integration import (
    validate_fsm_storage as _validate_fsm_storage,
)
from aiogram_nav.navigation import Navigation

from ...controls import handle_control
from ...coordinator import AiogramMemoryCoordinator, MemoryCoordinator
from ...errors import ConfigurationError, UnsupportedContext
from ...integration import _bind_bot as bind_idle_bot
from ...presentation import PromptTexts, TelegramPromptPresenter
from ...storage.redis_coordinator import RedisCoordinator
from .mapping import MappedCoordinator

if TYPE_CHECKING:
    from .integration import NavigationIntegration


class CombinedMiddleware(NavigationMiddleware):
    def __init__(
        self,
        integration: NavigationIntegration,
        navigation: Navigation,
        dispatcher: Dispatcher,
        *,
        manual: bool = False,
        allow_root_handlers: bool = False,
    ):
        super().__init__(
            navigation, dispatcher, manual=manual, allow_root_handlers=allow_root_handlers
        )
        self.integration = integration
        self.idle_coordinator = integration.idle.coordinator

    def validate(self) -> None:
        self.integration.validate()
        super().validate()
        coordinator = self.integration.idle.coordinator
        if (
            coordinator is not self.idle_coordinator
            or cast(
                MappedCoordinator, self.integration.navigation_repository.coordinator
            ).underlying
            is not coordinator
        ):
            raise ConfigurationError("Integrated coordinator changed after installation")
        if isinstance(self.isolation, (SimpleEventIsolation, TrackedEventIsolation)):
            actual = (
                coordinator.fsm_isolation
                if isinstance(coordinator, RedisCoordinator)
                else (
                    coordinator.isolation
                    if isinstance(coordinator, AiogramMemoryCoordinator)
                    else None
                )
            )
            if actual is not self.isolation:
                raise ConfigurationError(
                    "Shared coordinator no longer uses the verified FSM isolation"
                )

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)
        self.validate()
        idle, nav = self.integration.idle, self.navigation
        bot = data.get("bot")
        if not isinstance(bot, Bot):
            raise ConfigurationError("Dispatcher did not supply a Bot")
        try:
            key = await (nav.identity or private_identity)(event, bot, nav.namespace)
            if key is None:
                return await handler(event, data)
            # Supported custom resolvers may opt out; they cannot silently erase
            # topic/business/actor fields from the shared private identity.
            if key != await private_identity(event, bot, nav.namespace):
                raise ConfigurationError("Integrated resolver must preserve normalized identity")
        except (NavUnsupportedContext, UnsupportedContext):
            payload = event.event
            if isinstance(payload, CallbackQuery) and (payload.data or "").startswith(
                ("nav:", "idle:")
            ):
                await _ack(bot, payload.id, "This control is no longer active.")
                return None
            raise
        if key.namespace != idle.namespace or key.bot_id != bot.id:
            raise ConfigurationError("Navigation identity differs from idle runtime")
        payload = event.event
        if isinstance(payload, (Message, CallbackQuery)):
            actor = payload.from_user
            message = payload.message if isinstance(payload, CallbackQuery) else payload
            if (
                actor is None
                or message is None
                or key.chat_id != message.chat.id
                or key.user_id != actor.id
            ):
                raise ConfigurationError("Integrated identity must preserve actual actor and chat")
        mapped = self.integration.navigation_repository.mapping.to_idle(key)
        if key.tenant_id is not None:
            raise ConfigurationError("Default FSM mapping cannot represent tenant scope")
        _bind_bot(nav, bot)
        bind_idle_bot(idle, bot)
        state = data.get("state")
        if isinstance(state, FSMContext) and (
            state.key != StorageKey(bot_id=key.bot_id, chat_id=key.chat_id, user_id=key.user_id)
            or state.storage is not self.storage
        ):
            raise ConfigurationError("FSM context does not match shared conversation ownership")
        coordinator = idle.coordinator
        if self.fsm_enabled and isinstance(
            self.isolation, (SimpleEventIsolation, TrackedEventIsolation)
        ):
            if not isinstance(state, FSMContext):
                raise ConfigurationError(
                    "Borrowing the held FSM lock requires its original context"
                )
            if isinstance(coordinator, AiogramMemoryCoordinator):
                scope = coordinator.borrowed(mapped)
            elif isinstance(coordinator, RedisCoordinator):
                scope = coordinator.borrowed_fsm(mapped)
            else:
                raise ConfigurationError("Unsupported integrated FSM coordinator")
        else:
            scope = coordinator.hold(mapped)
        async with scope:
            self.validate()
            if isinstance(state, FSMContext):
                data["raw_state"] = await state.get_state()
                self.validate()
            if nav.draining:
                raise ConfigurationError("Navigation is draining")
            context = nav.for_conversation(key, operation_prefix=f"update:{event.update_id}")
            data.update(
                nav_context=context,
                navigation_context=context,
                nav_key=key,
                idle_context=idle.for_conversation(mapped),
                idle_key=mapped,
                navigation_integration=self.integration,
            )
            reserved = isinstance(payload, CallbackQuery) and (payload.data or "").startswith(
                "nav:"
            )
            if self.manual and reserved and isinstance(payload, CallbackQuery):
                if not await callback_is_current(nav, payload, context):
                    await nav.reject_callback(payload, bot, "stale")
                    return None
            if isinstance(payload, (Message, CallbackQuery)):
                prompt = await idle.current_prompt(mapped)
                presenter = idle.presenter
                texts = (
                    presenter.texts(prompt.locale if prompt else "en")
                    if isinstance(presenter, TelegramPromptPresenter)
                    else PromptTexts()
                )
                nav_pending = await nav.is_busy(key)
                if nav_pending:
                    # A partial navigation owns recovery. An old prompt must
                    # not reserve a competing idle operation against its view.
                    if await idle.is_busy(mapped) or not await _is_navigation_input(
                        nav, payload, context, bot
                    ):
                        if isinstance(payload, CallbackQuery):
                            await _ack(bot, payload.id, texts.busy)
                        return None
                else:
                    if await handle_control(
                        idle, payload, mapped, bot=bot, texts=texts, update_id=event.update_id
                    ):
                        return None
                    if await idle.is_busy(mapped):
                        if isinstance(payload, CallbackQuery):
                            await _ack(bot, payload.id, texts.busy)
                        return None
            self.validate()
            result = await handler(event, data)
            if self.manual and reserved and not context.control_handled:
                logging.getLogger(__name__).warning(
                    "Reserved navigation callback was not handled in manual routing"
                )
            return result


def validate_install(
    integration: NavigationIntegration,
    dispatcher: Dispatcher,
    navigation: Navigation,
    *,
    bindings_mode: str = "automatic",
    bindings_router: Router | None = None,
    allow_root_handlers: bool = False,
) -> None:
    """Reject incompatible setup before binding presenters or changing locks."""
    integration.validate()
    if bindings_mode not in {"automatic", "manual"} or type(allow_root_handlers) is not bool:
        raise ConfigurationError("Invalid combined routing configuration")
    manual = bindings_mode == "manual"
    if not manual and (bindings_router is not None or allow_root_handlers):
        raise ConfigurationError("Custom routing requires manual mode")
    if manual and navigation.bindings is not None:
        if bindings_router is None or bindings_router is not navigation.bindings_router:
            raise ConfigurationError("Use create_bindings_router for this Navigation")
        parent: Router | None = bindings_router
        while parent is not None and parent is not dispatcher:
            parent = parent.parent_router
        if parent is None:
            raise ConfigurationError("Include the bindings router before installation")
    if dispatcher.get("_aiogram_idle_installed") or dispatcher.get("_aiogram_nav_installed"):
        raise ConfigurationError(
            "Install the combined integration instead of separate idle/nav middleware"
        )
    if navigation._installed or integration.idle._installed:
        raise ConfigurationError("Integrated runtimes must be uninstalled and stopped")
    if dispatcher.fsm.strategy != FSMStrategy.USER_IN_CHAT:
        raise ConfigurationError("Integrated navigation requires FSMStrategy.USER_IN_CHAT")
    _validate_fsm_storage(dispatcher)
    bindings = navigation.bindings
    if bindings is not None:
        bindings.validate(navigation.registry)
        if not allow_root_handlers and (
            dispatcher.message.handlers or dispatcher.callback_query.handlers
        ):
            raise ConfigurationError("Use business Routers after integrated navigation bindings")
    isolation = dispatcher.fsm.events_isolation
    coordinator = integration.idle.coordinator
    if integration.idle._task is not None or coordinator.active_scopes:
        raise ConfigurationError("Install integrated middleware before starting protected work")
    if not isinstance(coordinator, BorrowedFsmCoordinator) and type(coordinator) not in {
        MemoryCoordinator,
        AiogramMemoryCoordinator,
        RedisCoordinator,
    }:
        raise ConfigurationError("Unsupported integrated coordinator implementation")
    mapped = integration.navigation_repository.coordinator
    if not isinstance(mapped, MappedCoordinator) or mapped.underlying is not coordinator:
        raise ConfigurationError("Integrated navigation must use its shared coordinator")
    if type(isolation) not in {SimpleEventIsolation, DisabledEventIsolation} and not isinstance(
        isolation, TrackedEventIsolation
    ):
        raise ConfigurationError(
            "Only verified SimpleEventIsolation or disabled isolation is supported"
        )


def install(
    integration: NavigationIntegration,
    dispatcher: Dispatcher,
    navigation: Navigation,
    *,
    lifecycle: bool,
    bindings_mode: str = "automatic",
    bindings_router: Router | None = None,
    allow_root_handlers: bool = False,
) -> None:
    validate_install(
        integration,
        dispatcher,
        navigation,
        bindings_mode=bindings_mode,
        bindings_router=bindings_router,
        allow_root_handlers=allow_root_handlers,
    )
    bindings = navigation.bindings
    isolation = dispatcher.fsm.events_isolation
    coordinator = integration.idle.coordinator
    if isinstance(isolation, (SimpleEventIsolation, TrackedEventIsolation)):
        if isinstance(coordinator, BorrowedFsmCoordinator):
            coordinator.configure_fsm_isolation(isolation)
        elif isinstance(coordinator, AiogramMemoryCoordinator):
            if coordinator.isolation is not isolation:
                raise ConfigurationError("Integrated runtimes require the same FSM isolation")
        elif type(coordinator) is MemoryCoordinator and not (
            integration.idle._explicit_coordinator
            or getattr(integration.idle.backend, "_explicit_coordinator", False)
        ):
            integration.idle.coordinator = AiogramMemoryCoordinator(isolation)
            cast(
                MappedCoordinator, integration.navigation_repository.coordinator
            ).underlying = integration.idle.coordinator
        else:
            raise ConfigurationError("Unsupported integrated coordination")
    elif type(isolation) is not DisabledEventIsolation:
        raise ConfigurationError(
            "Only verified SimpleEventIsolation or disabled isolation is supported"
        )
    manual = bindings_mode == "manual"
    middleware = CombinedMiddleware(
        integration, navigation, dispatcher, manual=manual, allow_root_handlers=allow_root_handlers
    )
    dispatcher.update.outer_middleware(middleware)
    if bindings is not None:
        if manual:
            middleware.bindings_router = bindings_router
        else:
            router = create_bindings_router(navigation)
            dispatcher.include_router(router)
            dispatcher.sub_routers.remove(router)
            dispatcher.sub_routers.insert(0, router)
            middleware.bindings_router = router
    dispatcher["_aiogram_idle_installed"] = dispatcher["_aiogram_nav_installed"] = True
    integration.idle._installed = navigation._installed = True
    if lifecycle:

        async def startup(bot: Bot) -> None:
            _bind_bot(navigation, bot)
            bind_idle_bot(integration.idle, bot)
            await integration.idle.start()

        async def shutdown() -> None:
            await integration.idle.stop()

        dispatcher.startup.register(startup)
        dispatcher.shutdown.register(shutdown)
        # Dispatcher registers FSM.close at construction. Workers must drain
        # while their shared FSM storage and isolation are still available.
        dispatcher.shutdown.handlers.insert(0, dispatcher.shutdown.handlers.pop())
