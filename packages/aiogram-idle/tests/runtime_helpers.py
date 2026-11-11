"""End-to-end memory runtime tests with deterministic time and effect barriers."""

import asyncio
from dataclasses import dataclass

from aiogram_idle.clock import ManualClock
from aiogram_idle.config import IdleConfig
from aiogram_idle.controls import ControlContext
from aiogram_idle.models import (
    ActionReceipt,
    ActivitySnapshot,
    FlowContext,
    FlowEligibility,
    IdleConversationKey,
    MessageRef,
    Phase,
)
from aiogram_idle.policies import ExemptPolicy, IdlePolicies, PromptPolicy
from aiogram_idle.presentation import DeliveryReceipt, FinishRequest, PromptReceipt, PromptRequest
from aiogram_idle.runtime import IdleRuntime
from aiogram_idle.storage.memory import MemoryIdleBackend


class Adapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.eligibility = FlowEligibility()
        self.inspect_errors: list[Exception] = []
        self.resume_result = ActionReceipt()
        self.restore_result = ActionReceipt(disposition="disarm")
        self.restore_error: Exception | None = None
        self.resume_error: Exception | None = None
        self.restore_entered: asyncio.Event | None = None
        self.restore_release: asyncio.Event | None = None

    async def inspect(self, context: FlowContext) -> FlowEligibility:
        self.calls.append("inspect")
        if self.inspect_errors:
            raise self.inspect_errors.pop(0)
        assert context.activity.params["draft_id"] == "draft"
        return self.eligibility

    async def resume(self, context: FlowContext, *, operation_id: str) -> ActionReceipt:
        self.calls.append("resume")
        if self.resume_error:
            raise self.resume_error
        return self.resume_result

    async def abandon(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        self.calls.append(f"abandon:{reason}")
        return ActionReceipt(disposition="disarm")

    async def restore(
        self, context: FlowContext, *, reason: str, operation_id: str
    ) -> ActionReceipt:
        self.calls.append(f"restore:{reason}")
        if self.restore_entered is not None:
            self.restore_entered.set()
        if self.restore_release is not None:
            await self.restore_release.wait()
        if self.restore_error:
            raise self.restore_error
        return self.restore_result


class Presenter:
    def __init__(self, clock: ManualClock) -> None:
        self.clock = clock
        self.questions: list[PromptRequest] = []
        self.finishes: list[FinishRequest] = []
        self.strips: list[PromptReceipt] = []
        self.show_errors: list[Exception] = []
        self.finish_error: Exception | None = None
        self.shown_at: float | None = None
        self.show_entered: asyncio.Event | None = None
        self.show_release: asyncio.Event | None = None

    async def show(self, request: PromptRequest) -> PromptReceipt:
        self.questions.append(request)
        if self.show_entered is not None:
            self.show_entered.set()
        if self.show_release is not None:
            await self.show_release.wait()
        if self.show_errors:
            raise self.show_errors.pop(0)
        return PromptReceipt(
            prompt_id=request.prompt_id,
            key=request.key,
            shown_at=self.clock.now() if self.shown_at is None else self.shown_at,
            controls=request.controls,
            locale=request.locale,
            continue_token=request.continue_token,
            cancel_token=request.cancel_token,
            messages=(MessageRef(request.key.chat_id, 100),),
        )

    async def finish(self, request: FinishRequest) -> DeliveryReceipt:
        self.finishes.append(request)
        if self.finish_error:
            raise self.finish_error
        return DeliveryReceipt()

    async def strip(self, receipt: PromptReceipt) -> DeliveryReceipt:
        self.strips.append(receipt)
        return DeliveryReceipt()


@dataclass
class Harness:
    runtime: IdleRuntime
    backend: MemoryIdleBackend
    clock: ManualClock
    adapter: Adapter
    presenter: Presenter
    key: IdleConversationKey
    activity: ActivitySnapshot

    async def due(self, advance: float = 10):
        self.clock.advance(advance)
        return await self.runtime.run_once()

    async def phase(self) -> Phase:
        record = await self.runtime.inspect(self.key)
        assert record is not None
        return record.idle.phase

    async def answer(
        self,
        action: str = "continue",
        *,
        transport: str = "commands",
        actor_id: int | None = None,
        operation_id: str = "answer",
    ):
        prompt = await self.runtime.current_prompt(self.key)
        assert prompt is not None
        context = ControlContext(
            self.key,
            actor_id or self.key.user_id,
            transport=transport,
            prompt_id=prompt.prompt_id,
            operation_id=operation_id,
            token=(prompt.continue_token if action == "continue" else prompt.cancel_token),
            message_id=100,
        )
        function = (
            self.runtime.continue_current if action == "continue" else self.runtime.cancel_current
        )
        return await function(context)


async def make_harness(
    *,
    enabled: bool = True,
    policy=None,
    lifetime: float = 1000,
    config: IdleConfig | None = None,
    on_event=None,
) -> Harness:
    clock = ManualClock(1000)
    config = config or IdleConfig(enabled=enabled)
    backend = MemoryIdleBackend(clock=clock, config=config)
    adapter, presenter = Adapter(), Presenter(clock)
    policies = IdlePolicies(
        {
            "draft": policy or PromptPolicy(after_seconds=10, grace_seconds=20),
            "skip": ExemptPolicy(),
        }
    )
    runtime = IdleRuntime(
        backend=backend,
        policies=policies,
        adapters={"form": adapter},
        presenter=presenter,
        namespace="test",
        on_event=on_event,
    )
    runtime.bot = None
    key = IdleConversationKey("test", 1, 2, 2)
    context = runtime.for_conversation(key)
    session = await context.open_session(operation_id="open", lifetime_seconds=lifetime)
    activity = await context.enter(
        "form.entry",
        policy_id="draft",
        adapter_key="form",
        params={"draft_id": "draft"},
        session_id=session.session_id,
        expires_at=session.expires_at,
        operation_id="enter",
    )
    return Harness(runtime, backend, clock, adapter, presenter, key, activity)
