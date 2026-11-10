"""Optional dispatcher wiring for standalone idle; no navigation dependency."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import KeyBuilder, StorageKey
from aiogram.fsm.storage.memory import DisabledEventIsolation, SimpleEventIsolation
from aiogram.fsm.strategy import FSMStrategy
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from .controls import ControlContext, ControlResult, handle_control
from .coordinator import AiogramMemoryCoordinator, MemoryCoordinator
from .errors import ConfigurationError, UnsupportedContext
from .models import IdleConversationKey, RuntimeSnapshot
from .presentation import PromptReceipt, PromptTexts, TelegramPromptPresenter
from .protocols import Coordinator, PromptPresenter
from .storage.redis_coordinator import RedisCoordinator

MiddlewareHandler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class IntegrationRuntime(Protocol):
    namespace: str

    @property
    def coordinator(self) -> Coordinator: ...

    @coordinator.setter
    def coordinator(self, value: Coordinator) -> None: ...

    presenter: PromptPresenter
    bot: Bot | None

    def for_conversation(self, key: IdleConversationKey) -> object: ...
    async def current_prompt(self, key: IdleConversationKey) -> PromptReceipt | None: ...
    async def continue_current(self, context: ControlContext) -> ControlResult: ...
    async def cancel_current(self, context: ControlContext) -> ControlResult: ...
    async def is_busy(self, key: IdleConversationKey) -> bool: ...
    async def inspect(self, key: IdleConversationKey) -> RuntimeSnapshot | None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


def private_identity(update: Update, bot: Bot, namespace: str) -> IdleConversationKey | None:
    """Resolve only actor-owned ordinary private chats; fail closed elsewhere."""
    event = update.event
    if not isinstance(event, (Message, CallbackQuery)):
        return None
    message = event.message if isinstance(event, CallbackQuery) else event
    actor = event.from_user
    if message is None or actor is None or message.chat.type != "private":
        raise UnsupportedContext("idle supports actor-owned private message conversations only")
    if getattr(message, "business_connection_id", None):
        raise UnsupportedContext("business conversations are not supported by the idle integration")
    return IdleConversationKey(namespace, bot.id, message.chat.id, actor.id)


class IdleContextMiddleware(BaseMiddleware):
    """Coordinate the complete handler and reserve explicit prompt controls first."""

    def __init__(
        self,
        runtime: IntegrationRuntime,
        *,
        fsm_enabled: bool = False,
        fsm_isolation: SimpleEventIsolation | None = None,
        dispatcher: Dispatcher | None = None,
    ) -> None:
        self.runtime = runtime
        self.fsm_enabled = fsm_enabled
        self.fsm_isolation = fsm_isolation
        self.dispatcher = dispatcher
        self._expected_isolation = dispatcher.fsm.events_isolation if dispatcher else None

    async def __call__(
        self,
        handler: MiddlewareHandler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)
        if self.dispatcher is not None:
            stack = list(self.dispatcher.update.outer_middleware)
            fsm_present = self.dispatcher.fsm in stack
            if (
                fsm_present != self.fsm_enabled
                or self not in stack
                or (fsm_present and stack.index(self.dispatcher.fsm) > stack.index(self))
                or self.dispatcher.fsm.events_isolation is not self._expected_isolation
            ):
                raise ConfigurationError(
                    "FSM middleware configuration changed after idle installation"
                )
        bot = data.get("bot")
        if not isinstance(bot, Bot):
            raise ConfigurationError("Dispatcher did not supply a Bot")
        key = private_identity(event, bot, self.runtime.namespace)
        if key is None:
            return await handler(event, data)
        _bind_bot(self.runtime, bot)
        coordinator = self.runtime.coordinator
        state = data.get("state")
        if isinstance(state, FSMContext):
            expected = StorageKey(bot_id=key.bot_id, chat_id=key.chat_id, user_id=key.user_id)
            if state.key != expected:
                raise ConfigurationError("FSM and idle conversation identities differ")
        if (
            self.fsm_enabled
            and isinstance(coordinator, AiogramMemoryCoordinator)
            and coordinator.isolation is self.fsm_isolation
            and isinstance(state, FSMContext)
        ):
            scope = coordinator.borrowed(key)
        elif (
            self.fsm_enabled
            and isinstance(coordinator, RedisCoordinator)
            and coordinator.fsm_isolation is self.fsm_isolation
            and self.fsm_isolation is not None
            and isinstance(state, FSMContext)
        ):
            scope = coordinator.borrowed_fsm(key)
        else:
            scope = coordinator.hold(key)
        async with scope:
            # Disabled FSM isolation may have loaded raw_state before our lock.
            if isinstance(state, FSMContext):
                data["raw_state"] = await state.get_state()
            data["idle_context"] = self.runtime.for_conversation(key)
            data["idle_key"] = key
            payload = event.event
            if isinstance(payload, (Message, CallbackQuery)):
                prompt = await self.runtime.current_prompt(key)
                presenter = self.runtime.presenter
                texts = (
                    presenter.texts(prompt.locale if prompt else "en")
                    if isinstance(presenter, TelegramPromptPresenter)
                    else PromptTexts()
                )
                if await handle_control(
                    self.runtime,
                    payload,
                    key,
                    bot=bot,
                    texts=texts,
                    update_id=event.update_id,
                ):
                    return None
                if await self.runtime.is_busy(key):
                    status = await self.runtime.inspect(key)
                    pending = status.idle.prompt if status is not None else None
                    if isinstance(presenter, TelegramPromptPresenter):
                        texts = presenter.texts(
                            pending.locale if pending and pending.locale else "en"
                        )
                    if isinstance(payload, CallbackQuery):
                        await bot.answer_callback_query(payload.id, text=texts.busy)
                    else:
                        await bot.send_message(payload.chat.id, texts.busy, parse_mode=None)
                    return None
            return await handler(event, data)


def install(
    runtime: IntegrationRuntime,
    dispatcher: Dispatcher,
    *,
    lifecycle: bool = True,
    manual_lifecycle: bool = False,
) -> None:
    """Install once, after aiogram's built-in FSM middleware.

    A verified SimpleEventIsolation is shared with workers. Redis workers acquire
    that local lock before the distributed lock, matching the incoming handler
    order. Middleware borrows the actual held FSM lock without recursive entry.
    With disabled FSM isolation the package coordinator covers the full handler.
    Custom FSM isolation requires an explicit adapter.
    """
    if dispatcher.get("_aiogram_idle_installed"):
        raise ConfigurationError("aiogram-idle is already installed on this dispatcher")
    isolation = dispatcher.fsm.events_isolation
    if dispatcher.fsm.strategy != FSMStrategy.USER_IN_CHAT:
        raise ConfigurationError("The idle integration requires FSMStrategy.USER_IN_CHAT")
    distributed = getattr(runtime.coordinator, "distributed", False) is True
    if distributed:
        _validate_fsm_storage(dispatcher)
    if isinstance(isolation, SimpleEventIsolation) and isinstance(
        runtime.coordinator, RedisCoordinator
    ):
        runtime.coordinator.configure_fsm_isolation(isolation)
    elif isinstance(isolation, SimpleEventIsolation) and not distributed:
        current = runtime.coordinator
        if isinstance(current, AiogramMemoryCoordinator):
            if current.isolation is not isolation:
                raise ConfigurationError(
                    "Shared idle storage requires the same FSM isolation instance"
                )
        else:
            runtime.coordinator = AiogramMemoryCoordinator(isolation)
    elif isinstance(isolation, SimpleEventIsolation) and distributed:
        raise ConfigurationError("Distributed FSM isolation requires a verified RedisCoordinator")
    elif not isinstance(isolation, (DisabledEventIsolation, SimpleEventIsolation)):
        raise ConfigurationError(
            "Unsupported FSM isolation; configure an explicitly supported integration"
        )
    elif not distributed and not isinstance(runtime.coordinator, MemoryCoordinator):
        raise ConfigurationError("Disabled FSM isolation requires a MemoryCoordinator")
    dispatcher["_aiogram_idle_installed"] = True
    dispatcher.update.outer_middleware(
        IdleContextMiddleware(
            runtime,
            fsm_enabled=any(item is dispatcher.fsm for item in dispatcher.update.outer_middleware),
            fsm_isolation=isolation if isinstance(isolation, SimpleEventIsolation) else None,
            dispatcher=dispatcher,
        )
    )
    if lifecycle and not manual_lifecycle:

        async def startup(bot: Bot) -> None:
            _bind_bot(runtime, bot)
            await runtime.start()

        async def shutdown() -> None:
            await runtime.stop()

        dispatcher.startup.register(startup)
        dispatcher.shutdown.register(shutdown)


def _bind_bot(runtime: IntegrationRuntime, bot: Bot) -> None:
    if runtime.bot is not None and runtime.bot.id != bot.id:
        raise ConfigurationError("Use one IdleRuntime per Bot for the Telegram integration")
    if (
        isinstance(runtime.presenter, TelegramPromptPresenter)
        and runtime.presenter.bot is not None
        and runtime.presenter.bot.id != bot.id
    ):
        raise ConfigurationError("Presenter and dispatcher bot identities differ")
    runtime.bot = bot
    if isinstance(runtime.presenter, TelegramPromptPresenter) and runtime.presenter.bot is None:
        runtime.presenter.bot = bot


def _validate_fsm_storage(dispatcher: Dispatcher) -> None:
    """Reject known Redis FSM key builders that alias independently locked users."""
    if not any(
        cls.__module__ == "aiogram.fsm.storage.redis" and cls.__name__ == "RedisStorage"
        for cls in type(dispatcher.storage).__mro__
    ):
        return
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
        keys = [builder.build(key, "data") for key in identities]
        states = [builder.build(key, "state") for key in identities]
    except Exception as error:
        raise ConfigurationError(
            "Redis FSM key builder cannot encode supported identities"
        ) from error
    if len(set(keys + states)) != 8:
        raise ConfigurationError(
            "Redis FSM keys must separate bot, chat, user and field; "
            "configure DefaultKeyBuilder(with_bot_id=True)"
        )
