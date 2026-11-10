"""Question delivery and recovery preserve the original confirmed grace window."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .effects import OperationEffects
from .errors import EffectUnknown
from .models import Phase, RuntimeSnapshot, timestamp
from .policies import PromptPolicy
from .presentation import PromptRequest
from .storage.state import Claim

if TYPE_CHECKING:
    from .worker import IdleWorker


class _InsufficientLifetime(Exception):
    """No request was made because the promised grace no longer fits."""


async def deliver_question(
    self: IdleWorker, record: RuntimeSnapshot, effects: OperationEffects, claim: Claim | None
) -> None:
    # Reserved prompt state invariant.
    assert record.activity is not None and record.idle.prompt is not None  # nosec B101
    policy = await self.runtime.backend.frozen_policy(record.key)
    # Reserved prompt state invariant.
    assert isinstance(policy, PromptPolicy)  # nosec B101
    # Reserved prompt state invariant.
    assert record.idle.operation is not None  # nosec B101
    if record.idle.prompt.messages:
        if record.idle.operation.effects.get("question") != "confirmed":
            await effects.checkpoint("question", "confirmed")
        await finish_question(self, effects, claim, policy)
        return
    context = await self.context(record, effects)
    eligibility = await self.runtime.adapter(record.activity.adapter_key).inspect(context)
    policy = await self.runtime.backend.frozen_policy(record.key)
    # Reserved prompt state invariant.
    assert isinstance(policy, PromptPolicy)  # nosec B101
    expiry = min(
        record.session.expires_at,
        record.activity.expires_at,
        (
            eligibility.expires_at
            if eligibility.expires_at is not None
            else record.activity.expires_at
        ),
    )
    if (
        not eligibility.authorized
        or not eligibility.resumable
        or self.runtime.clock.now() + policy.grace_seconds > expiry
    ):
        current = await effects.record()
        await self.save(
            current,
            replace(current.idle, phase=Phase.RESTORING),
            step="ineligible",
            claim=claim,
        )
        await self.action(await effects.record(), effects, claim, reason="expired")
        return

    def before_question(current: RuntimeSnapshot, stage: str) -> None:
        if stage not in {"question", "question-message"}:
            return
        operation = current.idle.operation
        if operation is not None and operation.effects.get("question-message") == "confirmed":
            return  # Recovery of a known message does not restart its grace.
        if self.runtime.clock.now() + policy.grace_seconds > expiry:
            raise _InsufficientLifetime

    effects.before_effect = before_question
    prompt = record.idle.prompt
    if not prompt.locale:
        locale = await self.runtime.locale(record.key)
        prompt = replace(prompt, locale=locale)
        current = await effects.record()
        await self.save(current, replace(current.idle, prompt=prompt), step="locale", claim=claim)
    for token in (prompt.continue_token, prompt.cancel_token):
        await self.runtime.backend.reserve_control(
            record.key,
            token=token,
            prompt_id=prompt.prompt_id,
            activity_id=record.activity.activity_id,
            expires_at=min(
                record.activity.expires_at,
                record.idle.operation.started_at
                + max(
                    self.runtime.config.recovery_retention_seconds,
                    policy.grace_seconds + self.runtime.config.operation_timeout_seconds,
                ),
            ),
        )
    request = PromptRequest(
        key=record.key,
        prompt_id=prompt.prompt_id,
        continue_token=prompt.continue_token,
        cancel_token=prompt.cancel_token,
        controls=prompt.controls,
        locale=prompt.locale,
        bot=self.runtime.bot,
        activity=record.activity,
        now=self.runtime.clock.now(),
        effects=effects,
    )

    # Persist the actual message receipt before recording the show stage as confirmed.
    async def show() -> None:
        receipt = await self.runtime.presenter.show(request)
        timestamp(receipt.shown_at)
        if (
            receipt.prompt_id != prompt.prompt_id
            or receipt.key != record.key
            or receipt.continue_token != prompt.continue_token
            or receipt.cancel_token != prompt.cancel_token
            or receipt.controls != prompt.controls
            or not receipt.locale
            or any(
                ref.chat_id != record.key.chat_id
                or isinstance(ref.message_id, bool)
                or ref.message_id <= 0
                for ref in receipt.messages
            )
        ):
            raise ValueError("Presenter receipt does not match reserved identity")
        current = await effects.record()
        await self.save(current, replace(current.idle, prompt=receipt), step="receipt", claim=claim)

    latest = await effects.record()
    # Reserved prompt state invariant.
    assert latest.idle.operation is not None  # nosec B101
    if (
        latest.idle.operation.effects.get("question") == "started"
        and latest.idle.prompt is not None
        and latest.idle.prompt.messages
    ):
        await effects.checkpoint("question", "confirmed")
    else:
        try:
            await effects.run(
                "question",
                show,
                replay_safe=getattr(self.runtime.presenter, "replay_safe", False) is True,
            )
        except _InsufficientLifetime:
            effects.before_effect = None
            await effects.checkpoint("question", "not_sent")
            current = await effects.record()
            await self.save(
                current,
                replace(current.idle, phase=Phase.RESTORING),
                step="late-ineligible",
                claim=claim,
            )
            await self.action(await effects.record(), effects, claim, reason="expired")
            return
    await finish_question(self, effects, claim, policy)


async def finish_question(
    self: IdleWorker, effects: OperationEffects, claim: Claim | None, policy: PromptPolicy
) -> None:
    current = await effects.record()
    # Reserved prompt state invariant.
    assert current.idle.prompt is not None and current.idle.operation is not None  # nosec B101
    if any(value == "started" for value in current.idle.operation.effects.values()):
        raise EffectUnknown("Question has unfinished delegated effects")
    delivered = min(current.idle.prompt.shown_at, self.runtime.clock.now())
    current = await self.save(
        current,
        replace(
            current.idle,
            phase=Phase.PROMPTED,
            operation=None,
            deadline=delivered + policy.grace_seconds,
        ),
        step="shown",
        claim=claim,
    )
    await self.runtime.notify(current, "shown", effects.operation_id)
