"""One immutable decision-phase observation; never an authorization cache."""

from collections.abc import Mapping
from dataclasses import dataclass

from .models import Phase, RuntimeSnapshot
from .presentation import PromptReceipt


@dataclass(frozen=True)
class IdleObservation:
    record: RuntimeSnapshot | None
    prompt: PromptReceipt | None
    busy: bool
    navigation_pending: bool


def observe(record: RuntimeSnapshot | None, now: float) -> IdleObservation:
    prompt = None
    busy = False
    navigation_pending = False
    if record is not None:
        if (
            record.activity is not None
            and min(record.session.expires_at, record.activity.expires_at) > now
            and record.idle.phase in {Phase.PROMPTED, Phase.DELIVERY_UNKNOWN}
        ):
            prompt = record.idle.prompt
        busy = record.idle.operation is not None and record.idle.phase in {
            Phase.ACTIVE,
            Phase.PROMPT_PENDING,
            Phase.RESUMING,
            Phase.ABANDONING,
            Phase.RESTORING,
            Phase.EFFECT_UNKNOWN,
            Phase.QUARANTINED,
        }
        owner = record.components.get("__idle_owner__")
        navigation_pending = isinstance(owner, Mapping) and owner.get("pending") is True
    return IdleObservation(record, prompt, busy, navigation_pending)
