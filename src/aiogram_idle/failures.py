"""Failure classification distinguishes definite rejection from uncertain effects."""

from __future__ import annotations

from dataclasses import replace

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from .config import AmbiguousSendPolicy, IdleConfig
from .models import IdleSnapshot, Phase, RuntimeSnapshot


def classify_failure(
    record: RuntimeSnapshot,
    exc: Exception,
    now: float,
    config: IdleConfig,
    replay_safe_stages: frozenset[str] = frozenset(),
) -> tuple[IdleSnapshot, str]:
    operation = record.idle.operation
    # Caller requires a reserved operation.
    assert operation is not None  # nosec B101
    operation = replace(operation, failure_reason=type(exc).__name__[:64])
    record = replace(record, idle=replace(record.idle, operation=operation))
    uncertain = any(
        value == "started" and stage not in replay_safe_stages
        for stage, value in operation.effects.items()
    )
    if isinstance(exc, TelegramForbiddenError):
        return replace(record.idle, phase=Phase.QUARANTINED, deadline=None), "failed"
    known_rejection = isinstance(exc, TelegramRetryAfter) and not uncertain
    safe_preflight = not uncertain
    if known_rejection or safe_preflight:
        # A later state-commit failure must never erase confirmed external effects.
        operation = replace(operation, attempts=operation.attempts + 1)
        wait = exc.retry_after if isinstance(exc, TelegramRetryAfter) else config.poll_seconds
        exhausted = (
            operation.attempts >= config.retry_max_attempts
            or now + wait - operation.started_at >= config.retry_max_age_seconds
        )
        return replace(
            record.idle,
            operation=operation,
            phase=Phase.QUARANTINED if exhausted else record.idle.phase,
            deadline=None if exhausted else now + wait,
        ), "failed" if exhausted else "retry"
    question = record.idle.phase == Phase.PROMPT_PENDING
    phase = Phase.DELIVERY_UNKNOWN if question else Phase.EFFECT_UNKNOWN
    if isinstance(exc, TelegramForbiddenError):
        phase = Phase.QUARANTINED
    if question and config.ambiguous_send == AmbiguousSendPolicy.RETRY:
        operation = replace(
            operation,
            effects={key: value for key, value in operation.effects.items() if value != "started"},
            attempts=operation.attempts + 1,
        )
        exhausted = (
            operation.attempts >= config.retry_max_attempts
            or now - operation.started_at >= config.retry_max_age_seconds
        )
        phase = Phase.QUARANTINED if exhausted else Phase.PROMPT_PENDING
    return replace(
        record.idle,
        phase=phase,
        operation=operation,
        deadline=now + config.poll_seconds if phase == Phase.PROMPT_PENDING else None,
    ), "delivery_unknown" if phase == Phase.DELIVERY_UNKNOWN else "failed"
