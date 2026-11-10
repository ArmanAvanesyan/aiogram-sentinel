"""Recoverable lifecycle worker; no network request runs under the backend lock."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from .compat import bounded
from .effects import OperationEffects, internal_id
from .errors import ConfigurationError, EffectUnknown, IdleError, OwnershipLost
from .machine import Trigger, reduce_phase
from .models import (
    ActionReceipt,
    ActivitySnapshot,
    FlowContext,
    FlowEligibility,
    IdleSnapshot,
    PendingOperation,
    Phase,
    RuntimeSnapshot,
)
from .policies import ExemptPolicy, PromptPolicy
from .presentation import FinishRequest, PromptReceipt
from .storage.state import Claim

if TYPE_CHECKING:
    from .runtime import IdleRuntime


class IdleWorker:
    def __init__(self, runtime: IdleRuntime) -> None:
        self.runtime = runtime

    async def handle(self, claim: Claim) -> bool:
        work = asyncio.create_task(self._locked(claim))
        renewal = asyncio.create_task(self._renew(claim))
        try:
            done, _ = await asyncio.wait({work, renewal}, return_when=asyncio.FIRST_COMPLETED)
            if renewal in done:
                await renewal
                raise OwnershipLost("Lease renewal stopped")
            return await work
        except (IdleError, asyncio.TimeoutError):
            return False
        finally:
            work.cancel()
            renewal.cancel()
            await asyncio.gather(work, renewal, return_exceptions=True)
            with contextlib.suppress(OwnershipLost):
                await self.runtime.backend.release_claim(claim)

    async def _renew(self, claim: Claim) -> None:
        while True:
            await self.runtime.clock.sleep(self.runtime.config.renew_seconds)
            await self.runtime.backend.renew_claim(
                claim,
                lease_seconds=self.runtime.config.lease_seconds,
            )

    async def _locked(self, claim: Claim) -> bool:
        manager = self.runtime.coordinator.hold(claim.key)
        async with bounded(self.runtime.config.lock_wait_seconds):
            await manager.__aenter__()
        try:
            await self.runtime.backend.validate_claim(claim)
            record = await self.runtime.backend.load(claim.key)
            if record is not None:
                async with bounded(self.runtime.config.operation_timeout_seconds):
                    await self.execute(record, claim)
                latest = await self.runtime.backend.load(claim.key)
                return latest is not None and latest.idle.phase in {
                    Phase.ACTIVE,
                    Phase.PROMPTED,
                    Phase.DISARMED,
                }
            return False
        finally:
            await manager.__aexit__(None, None, None)

    async def save(
        self, record: RuntimeSnapshot, idle: IdleSnapshot, *, step: str, claim: Claim | None
    ) -> RuntimeSnapshot:
        operation = idle.operation or record.idle.operation
        operation_id = (
            operation.operation_id
            if operation
            else f"{record.session.session_id}:{record.store_version}:{step}"
        )
        return await self.runtime.backend.transition(
            record.key,
            expected_version=record.store_version,
            operation_id=internal_id(operation_id, step),
            fingerprint=f"{operation_id}:{step}",
            claim=claim,
            transform=lambda old: replace(old, idle=idle),
        )

    async def execute(self, record: RuntimeSnapshot, claim: Claim | None) -> None:
        try:
            await self._execute(record, claim)
        except asyncio.CancelledError:
            # The persisted request_started checkpoint is the recovery evidence.
            raise
        except OwnershipLost:
            raise
        except Exception as exc:
            current = await self.runtime.backend.load(record.key)
            if current is None or current.idle.operation is None:
                raise
            await self.record_failure(current, exc, claim)

    async def _execute(self, record: RuntimeSnapshot, claim: Claim | None) -> None:
        if self.runtime.component_validator is not None:
            self.runtime.component_validator()
        recovery = self.runtime.component_recovery
        if recovery is not None and await recovery(record, claim):
            return
        owner = record.components.get("__idle_owner__")
        if (
            isinstance(owner, Mapping)
            and owner.get("pending")
            and (recovery is None or record.idle.operation is None)
        ):
            raise ConfigurationError("Pending component recovery requires its owning integration")
        activity = record.activity
        now = self.runtime.clock.now()
        if activity is None or min(activity.expires_at, record.session.expires_at) <= now:
            operation = record.idle.operation
            if operation is not None:
                operation = replace(operation, failure_reason="logical_expiry")
            await self.save(
                record,
                replace(
                    record.idle,
                    phase=Phase.QUARANTINED if operation else Phase.DISARMED,
                    deadline=None,
                    operation=operation,
                ),
                step=f"expiry:{record.session.session_id}",
                claim=claim,
            )
            return
        if record.idle.phase == Phase.ACTIVE:
            if not await self.runtime.enabled():
                await self.save(
                    record, IdleSnapshot(), step=f"disabled:{activity.activity_id}", claim=claim
                )
                return
            policy = await self.runtime.backend.frozen_policy(record.key)
            if isinstance(policy, ExemptPolicy):
                return
            prompt = isinstance(policy, PromptPolicy)
            trigger = Trigger.DUE_PROMPT if prompt else Trigger.DUE_RESTORE
            operation = PendingOperation(
                operation_id=secrets.token_urlsafe(18),
                kind="prompt" if prompt else "restored",
                started_at=now,
            )
            receipt = (
                PromptReceipt(
                    prompt_id=secrets.token_urlsafe(16),
                    shown_at=now,
                    locale="",
                    controls=policy.controls if prompt else "inline",
                    key=record.key,
                    continue_token=secrets.token_urlsafe(18),
                    cancel_token=secrets.token_urlsafe(18),
                )
                if prompt
                else None
            )
            record = await self.save(
                record,
                IdleSnapshot(
                    phase=reduce_phase(record.idle.phase, trigger),
                    deadline=now,
                    operation=operation,
                    prompt=receipt,
                ),
                step="reserve",
                claim=claim,
            )
        elif record.idle.phase == Phase.PROMPTED:
            operation = PendingOperation(
                operation_id=secrets.token_urlsafe(18),
                kind="timed_out",
                started_at=now,
            )
            record = await self.save(
                record,
                replace(
                    record.idle,
                    phase=reduce_phase(record.idle.phase, Trigger.TIMEOUT),
                    operation=operation,
                ),
                step="reserve-timeout",
                claim=claim,
            )
        if record.idle.operation is None:
            return
        effects = OperationEffects(
            self.runtime, record.key, record.idle.operation.operation_id, claim
        )
        if record.idle.phase == Phase.PROMPT_PENDING:
            from .questions import deliver_question

            await deliver_question(self, record, effects, claim)
        elif record.idle.phase in {Phase.RESUMING, Phase.ABANDONING, Phase.RESTORING}:
            await self.action(record, effects, claim)

    async def context(self, record: RuntimeSnapshot, effects: OperationEffects) -> FlowContext:
        # Internal reserved-operation invariant.
        assert record.activity is not None and record.idle.operation is not None  # nosec B101
        dependencies: Mapping[str, object] = (
            await self.runtime.dependencies(record.key) if self.runtime.dependencies else {}
        )
        return FlowContext(
            key=record.key,
            activity=record.activity,
            operation_id=record.idle.operation.operation_id,
            now=self.runtime.clock.now(),
            prompt_id=record.idle.prompt.prompt_id if record.idle.prompt else None,
            bot=self.runtime.bot,
            dependencies=dependencies,
            effects=effects,
        )

    async def action(
        self,
        record: RuntimeSnapshot,
        effects: OperationEffects,
        claim: Claim | None,
        reason: str | None = None,
    ) -> None:
        # Internal reserved-operation invariant.
        assert record.activity is not None and record.idle.operation is not None  # nosec B101
        context = await self.context(record, effects)
        adapter = self.runtime.adapter(record.activity.adapter_key)
        kind = record.idle.operation.kind
        reason = reason or ("cancelled" if kind == "cancel" else kind)
        receipt = ActionReceipt(disposition="disarm")
        if record.idle.phase == Phase.RESUMING:
            eligibility = (
                await adapter.inspect(context)
                if record.idle.operation.effects.get("resume") != "confirmed"
                else FlowEligibility()
            )
            if (
                eligibility.authorized
                and eligibility.resumable
                and (
                    eligibility.expires_at is None
                    or eligibility.expires_at > self.runtime.clock.now()
                )
            ):
                receipt = await effects.run(
                    "resume",
                    lambda: adapter.resume(
                        context,
                        operation_id=context.operation_id,
                    ),
                    replay_safe=getattr(adapter, "replay_safe", False) is True,
                )
                outcome = "continued"
            else:
                await effects.run(
                    "abandon",
                    lambda: adapter.abandon(
                        context,
                        reason="expired",
                        operation_id=context.operation_id,
                    ),
                    replay_safe=getattr(adapter, "replay_safe", False) is True,
                )
                receipt = await effects.run(
                    "restore",
                    lambda: adapter.restore(
                        context,
                        reason="expired",
                        operation_id=context.operation_id,
                    ),
                    replay_safe=getattr(adapter, "replay_safe", False) is True,
                )
                outcome = "cancelled"
        else:
            await effects.run(
                "abandon",
                lambda: adapter.abandon(
                    context,
                    reason=reason,
                    operation_id=context.operation_id,
                ),
                replay_safe=getattr(adapter, "replay_safe", False) is True,
            )
            receipt = await effects.run(
                "restore",
                lambda: adapter.restore(
                    context,
                    reason=reason,
                    operation_id=context.operation_id,
                ),
                replay_safe=getattr(adapter, "replay_safe", False) is True,
            )
            outcome = (
                "cancelled"
                if kind == "cancel"
                else ("timed_out" if kind == "timed_out" else "restored")
            )
        current = await effects.record()
        prompt = current.idle.prompt
        if prompt is not None:
            await effects.run(
                "outcome",
                lambda: self.runtime.presenter.finish(
                    FinishRequest(
                        receipt=prompt,
                        outcome=outcome,
                        bot=self.runtime.bot,
                    )
                ),
                replay_safe=getattr(self.runtime.presenter, "replay_safe", False) is True,
            )
        await self._complete(await effects.record(), receipt, outcome, effects, claim)

    async def _complete(
        self,
        record: RuntimeSnapshot,
        receipt: ActionReceipt,
        outcome: str,
        effects: OperationEffects,
        claim: Claim | None,
    ) -> None:
        # Internal reserved-operation invariant.
        assert record.activity is not None and record.idle.operation is not None  # nosec B101
        if any(value == "started" for value in record.idle.operation.effects.values()):
            raise EffectUnknown("Operation has unfinished delegated effects")
        activity = record.activity
        now = self.runtime.clock.now()
        policy = await self.runtime.backend.frozen_policy(record.key)
        enabled = await self.runtime.enabled()
        phase, deadline = Phase.DISARMED, None
        if outcome == "continued" and receipt.disposition == "rearm":
            activity = replace(
                activity,
                activity_revision=activity.activity_revision + 1,
                last_activity_at=record.idle.operation.started_at,
            )
            if enabled and not isinstance(policy, ExemptPolicy):
                phase, deadline = Phase.ACTIVE, activity.last_activity_at + policy.after_seconds
        if receipt.replacement is not None:
            spec = receipt.replacement
            self.runtime.adapter(spec.adapter_key)
            policy = self.runtime.policies[spec.policy_id]
            expiry = min(
                spec.expires_at if spec.expires_at is not None else activity.expires_at,
                record.session.expires_at,
            )
            if expiry <= now:
                raise ValueError("Replacement activity already expired")
            activity = ActivitySnapshot(
                session_id=activity.session_id,
                activity_id=secrets.token_urlsafe(18),
                activity_key=spec.activity_key,
                activity_revision=1,
                policy_id=spec.policy_id,
                adapter_key=spec.adapter_key,
                params=spec.params,
                entered_at=now,
                last_activity_at=now,
                expires_at=expiry,
            )
            if enabled and not isinstance(policy, ExemptPolicy):
                phase, deadline = Phase.ACTIVE, now + policy.after_seconds
        changed = replace(
            record, activity=activity, idle=IdleSnapshot(phase=phase, deadline=deadline)
        )
        if self.runtime.component_validator is not None:
            self.runtime.component_validator()
        finalizer = self.runtime.component_finalizer
        if receipt.component_updates:
            if finalizer is None:
                raise ConfigurationError("Component completion requires its owning integration")
            changed = replace(
                changed, components={**changed.components, **receipt.component_updates}
            )
        if finalizer is not None:
            changed = finalizer(record, changed, receipt)
        committed = await self.runtime.backend.transition(
            record.key,
            expected_version=record.store_version,
            operation_id=internal_id(effects.operation_id, "complete"),
            fingerprint=f"{effects.operation_id}:complete",
            transform=lambda _: changed,
            claim=claim,
            policy=policy,
        )
        observer = self.runtime.component_after_commit
        if observer is not None:
            try:
                if self.runtime.component_validator is not None:
                    self.runtime.component_validator()
                await observer(record, committed, receipt)
            except Exception:
                import logging

                logging.getLogger(__name__).warning("Component cleanup unavailable after commit")
        await self.runtime.notify(record, outcome, effects.operation_id)

    async def record_failure(
        self, record: RuntimeSnapshot, exc: Exception, claim: Claim | None
    ) -> None:
        from .failures import classify_failure

        safe_stages: set[str] = set()
        if getattr(self.runtime.presenter, "replay_safe", False) is True:
            safe_stages.update({"question", "outcome"})
        if (
            record.activity is not None
            and getattr(
                self.runtime.adapters.get(record.activity.adapter_key), "replay_safe", False
            )
            is True
        ):
            safe_stages.update({"resume", "abandon", "restore"})
        idle, outcome = classify_failure(
            record, exc, self.runtime.clock.now(), self.runtime.config, frozenset(safe_stages)
        )
        operation = idle.operation
        # Internal reserved-operation invariant.
        assert operation is not None  # nosec B101
        await self.save(
            record,
            idle,
            step=f"failure:{operation.attempts}:{self.runtime.clock.now()}",
            claim=claim,
        )
        if outcome != "retry":
            await self.runtime.notify(record, outcome, operation.operation_id)
