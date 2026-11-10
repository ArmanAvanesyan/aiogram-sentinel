"""Standalone runtime: activity, controls and worker lifecycle share coordination."""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from aiogram_coordination import ExternalSession, SessionAuthority

from .activity import IdleContext
from .compat import bounded
from .config import IdleConfig
from .controls import ControlContext, ControlResult
from .errors import ConfigurationError, ConfigurationMismatch, SessionExpired
from .events import EventSink, emit
from .machine import Trigger, reduce_phase
from .models import (
    ActionReceipt,
    ConfigManifest,
    ConfigUpdate,
    IdleConversationKey,
    IdleEvent,
    PendingOperation,
    Phase,
    PollReport,
    ReconcileReport,
    RuntimeSnapshot,
)
from .policies import IdlePolicies
from .presentation import PromptReceipt, TelegramPromptPresenter
from .protocols import Coordinator, FlowAdapter, PromptPresenter
from .storage.base import IdleBackend
from .storage.state import Claim

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher

logger = logging.getLogger(__name__)
DependencyFactory = Callable[[IdleConversationKey], Awaitable[Mapping[str, object]]]
ComponentFinalizer = Callable[[RuntimeSnapshot, RuntimeSnapshot, ActionReceipt], RuntimeSnapshot]
ComponentRecovery = Callable[[RuntimeSnapshot, Claim | None], Awaitable[bool]]
ComponentObserver = Callable[[RuntimeSnapshot, RuntimeSnapshot, ActionReceipt], Awaitable[None]]


class IdleRuntime:
    def __init__(
        self,
        *,
        backend: IdleBackend,
        policies: IdlePolicies,
        adapters: Mapping[str, FlowAdapter],
        presenter: PromptPresenter,
        config: IdleConfig | None = None,
        namespace: str = "default",
        isolation: Coordinator | None = None,
        dependencies: DependencyFactory | None = None,
        locale_resolver: Callable[[IdleConversationKey], Awaitable[str]] | None = None,
        on_event: EventSink | None = None,
        session_authority: SessionAuthority | None = None,
        bot: Bot | None = None,
    ) -> None:
        presenter_bot = presenter.bot if isinstance(presenter, TelegramPromptPresenter) else None
        if bot is not None and presenter_bot is not None and bot.id != presenter_bot.id:
            raise ConfigurationError("Runtime and presenter bot identities differ")
        self.bot = bot or presenter_bot
        self.backend = backend
        self.clock = backend.clock
        self.policies = policies
        self.adapters = dict(adapters)
        self.presenter = presenter
        self.config = config or backend.config
        self.namespace = namespace
        self._explicit_coordinator = isolation is not None or getattr(
            backend, "_explicit_coordinator", False
        )
        if isolation is not None:
            backend.bind_coordinator(isolation)
        self.dependencies = dependencies
        self.on_event = on_event
        self._session_authority = session_authority
        self.locale_resolver = locale_resolver
        # Optional generic component hooks are registered before startup by a
        # transaction-owning integration. Core never interprets its payload.
        self.component_finalizer: ComponentFinalizer | None = None
        self.component_recovery: ComponentRecovery | None = None
        self.component_after_commit: ComponentObserver | None = None
        self._component_validator: Callable[[], None] | None = None
        self._initialized = False
        self._initialize_lock = asyncio.Lock()
        self._poll_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._wake = asyncio.Event()
        self._installed = False
        if not namespace or len(namespace) > 128:
            raise ConfigurationError("Invalid namespace")
        if not self.adapters:
            raise ConfigurationError("At least one flow adapter is required")
        from .worker import IdleWorker

        self.worker = IdleWorker(self)

    @property
    def session_authority(self) -> SessionAuthority | None:
        return self._session_authority

    @property
    def component_validator(self) -> Callable[[], None] | None:
        return self._component_validator

    @component_validator.setter
    def component_validator(self, value: Callable[[], None] | None) -> None:
        if self._component_validator is not None and value != self._component_validator:
            raise ConfigurationError("An integration ownership validator cannot be replaced")
        self._component_validator = value

    @property
    def coordinator(self) -> Coordinator:
        return self.backend.coordinator

    @coordinator.setter
    def coordinator(self, value: Coordinator) -> None:
        self._explicit_coordinator = True
        self.backend.bind_coordinator(value)

    def adapter(self, key: str) -> FlowAdapter:
        try:
            return self.adapters[key]
        except KeyError as exc:
            raise ConfigurationError("Unknown flow adapter") from exc

    async def locale(self, key: IdleConversationKey) -> str:
        locale = await self.locale_resolver(key) if self.locale_resolver else "en"
        if not locale or len(locale) > 32:
            raise ConfigurationError("Locale resolver returned an invalid locale")
        return locale

    async def external_session(self, key: IdleConversationKey) -> ExternalSession:
        from .sessions import current_external

        return await current_external(self, key)

    async def authorize(
        self, record: RuntimeSnapshot, *, observation: ExternalSession | None = None
    ) -> ExternalSession | None:
        from .sessions import authorize

        return await authorize(self, record, observation=observation)

    async def initialize(self) -> None:
        if self.component_validator is not None:
            self.component_validator()
        async with self._initialize_lock:
            if not self._initialized:
                await self.backend.bootstrap_config(
                    enabled=self.config.enabled, policies_digest=self.policies.digest
                )
                self._initialized = True

    async def manifest(self) -> ConfigManifest:
        await self.initialize()
        manifest = await self.backend.get_config()
        if manifest is None or manifest.policies_digest != self.policies.digest:
            raise ConfigurationMismatch("Runtime policies differ from authoritative manifest")
        return manifest

    async def enabled(self) -> bool:
        return (await self.manifest()).enabled

    async def apply_config(
        self,
        *,
        expected_generation: str,
        update: ConfigUpdate,
    ) -> ConfigManifest:
        await self.initialize()
        return await self.backend.apply_config(
            expected_generation=expected_generation,
            enabled=update.enabled,
            policies_digest=self.policies.digest,
            operation_id=update.operation_id,
        )

    def for_conversation(self, key: IdleConversationKey) -> IdleContext:
        if key.namespace != self.namespace:
            raise ConfigurationError("Conversation namespace differs from runtime")
        return IdleContext(self, key)

    async def inspect(self, key: IdleConversationKey) -> RuntimeSnapshot | None:
        return await self.backend.load(key)

    async def is_busy(self, key: IdleConversationKey) -> bool:
        record = await self.backend.load(key)
        return (
            record is not None
            and record.idle.operation is not None
            and record.idle.phase
            in {
                Phase.ACTIVE,
                Phase.PROMPT_PENDING,
                Phase.RESUMING,
                Phase.ABANDONING,
                Phase.RESTORING,
                Phase.EFFECT_UNKNOWN,
                Phase.QUARANTINED,
            }
        )

    async def current_prompt(self, key: IdleConversationKey) -> PromptReceipt | None:
        record = await self.backend.load(key)
        if (
            record is None
            or record.activity is None
            or min(record.session.expires_at, record.activity.expires_at) <= self.clock.now()
            or record.idle.phase not in {Phase.PROMPTED, Phase.DELIVERY_UNKNOWN}
        ):
            return None
        return record.idle.prompt

    async def notify(self, record: RuntimeSnapshot, outcome: str, operation_id: str) -> None:
        await emit(
            self.on_event,
            IdleEvent(
                event_id=f"{operation_id}:{outcome}",
                operation_id=operation_id,
                key=record.key,
                outcome=outcome,
                at=self.clock.now(),
                activity_key=record.activity.activity_key if record.activity else "",
                prompt_id=record.idle.prompt.prompt_id if record.idle.prompt else None,
            ),
        )

    async def continue_current(self, context: ControlContext) -> ControlResult:
        return await self._answer(context, "continue")

    async def cancel_current(self, context: ControlContext) -> ControlResult:
        return await self._answer(context, "cancel")

    async def _answer(self, context: ControlContext, action: str) -> ControlResult:
        await self.initialize()
        if context.key.namespace != self.namespace or context.transport not in {
            "inline",
            "reply",
            "commands",
        }:
            return ControlResult(False, "stale")
        async with self.coordinator.hold(context.key):
            record = await self.backend.load(context.key)
            if (
                record is None
                or record.activity is None
                or isinstance(context.actor_id, bool)
                or context.actor_id != context.key.user_id
            ):
                return ControlResult(False, "stale")
            try:
                await self.authorize(record)
            except SessionExpired:
                from .sessions import retire

                await retire(self, record)
                return ControlResult(False, "expired")
            owner = record.components.get("__idle_owner__")
            if isinstance(owner, Mapping) and owner.get("pending") is True:
                return ControlResult(False, "busy")
            prompt = await self.current_prompt(context.key)
            if prompt is None or context.prompt_id not in {None, prompt.prompt_id}:
                return ControlResult(False, "stale")
            if (
                record.idle.phase is Phase.PROMPTED
                and record.idle.deadline is not None
                and record.idle.deadline <= self.clock.now()
            ):
                return ControlResult(False, "expired")
            if context.transport == "inline":
                expected = prompt.continue_token if action == "continue" else prompt.cancel_token
                if not context.token or not hmac.compare_digest(context.token, expected):
                    return ControlResult(False, "stale")
                token = await self.backend.resolve_control(context.key, context.token)
                if token is None or token.prompt_id != prompt.prompt_id:
                    return ControlResult(False, "stale")
                if prompt.messages and context.message_id != prompt.messages[0].message_id:
                    return ControlResult(False, "stale")
            operation_id = context.operation_id or f"answer:{prompt.prompt_id}:{action}"
            trigger = Trigger.CONTINUE if action == "continue" else Trigger.CANCEL
            phase = reduce_phase(record.idle.phase, trigger)
            operation = PendingOperation(
                operation_id=operation_id,
                kind=action,
                started_at=self.clock.now(),
            )
            record = await self.backend.transition(
                context.key,
                expected_version=record.store_version,
                operation_id=operation_id,
                fingerprint=f"answer:{record.activity.activity_id}:{prompt.prompt_id}:{action}",
                transform=lambda old: replace(
                    old,
                    idle=replace(
                        old.idle,
                        phase=phase,
                        operation=operation,
                        deadline=self.clock.now(),
                    ),
                ),
            )
            # A recovery job is now persisted before executing application effects.
            try:
                async with bounded(self.config.operation_timeout_seconds):
                    await self.worker.execute(record, claim=None)
            except asyncio.TimeoutError:
                current = await self.backend.load(context.key)
                if current is not None and current.idle.operation is not None:
                    from .errors import EffectUnknown

                    await self.worker.record_failure(
                        current, EffectUnknown("Control effect timed out"), None
                    )
            current = await self.backend.load(context.key)
            if current is not None and current.idle.operation is not None:
                return ControlResult(True, current.idle.phase.value)
            if current is not None and current.idle.phase in {
                Phase.EFFECT_UNKNOWN,
                Phase.DELIVERY_UNKNOWN,
                Phase.QUARANTINED,
            }:
                return ControlResult(True, current.idle.phase.value)
            return ControlResult(True, "continued" if action == "continue" else "cancelled")

    def install(self, dispatcher: Dispatcher, *, lifecycle: bool = True) -> None:
        from .integration import install

        if self._installed:
            raise ConfigurationError("IdleRuntime is already installed")
        install(self, dispatcher, lifecycle=lifecycle)
        self._installed = True

    async def run_once(self, *, limit: int | None = None) -> PollReport:
        await self.initialize()
        async with self._poll_lock:
            if self._stopping:
                return PollReport()
            capacity = (
                self.config.claim_limit if limit is None else min(limit, self.config.claim_limit)
            )
            if capacity < 1:
                raise ValueError("Worker limit must be positive")
            claims = await self.backend.claim_due(
                limit=capacity,
                lease_seconds=self.config.lease_seconds,
                namespace=self.namespace,
                bot_id=self.bot.id if self.bot is not None else None,
            )
            outcomes = await asyncio.gather(
                *(self.worker.handle(claim) for claim in claims), return_exceptions=True
            )
            for outcome in outcomes:
                if isinstance(outcome, asyncio.CancelledError):
                    raise outcome
            return PollReport(
                claimed=len(claims),
                completed=sum(value is True for value in outcomes),
                failed=sum(value is not True for value in outcomes),
            )

    async def reconcile(self, *, limit: int = 100) -> ReconcileReport:
        repaired = await self.backend.reconcile(limit=limit)
        return ReconcileReport(repaired=repaired)

    async def start(self) -> None:
        await self.initialize()
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._wake.clear()
        self._task = asyncio.create_task(self._loop(), name="aiogram-idle")

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                await self.run_once()
                await self.reconcile()
            except asyncio.CancelledError:
                task = asyncio.current_task()
                cancelling = getattr(task, "cancelling", lambda: 0)()
                if self._stopping or cancelling:
                    raise
                logger.warning("Idle worker cancellation retained for recovery")
            except Exception:
                logger.warning("Idle polling encountered a guarded runtime failure")
            sleeper = asyncio.create_task(self.clock.sleep(self.config.poll_seconds))
            wake = asyncio.create_task(self._wake.wait())
            try:
                await asyncio.wait({sleeper, wake}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                sleeper.cancel()
                wake.cancel()
                await asyncio.gather(sleeper, wake, return_exceptions=True)

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        task = self._task
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=self.config.shutdown_seconds)
            except asyncio.TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            finally:
                self._task = None
