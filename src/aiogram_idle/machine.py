"""Pure lifecycle reducer: effects run only after the transition is reserved."""

from __future__ import annotations

from enum import Enum

from .errors import ActivityConflict
from .models import Phase


class Trigger(str, Enum):
    ENTER = "enter"
    TOUCH = "touch"
    CLEAR = "clear"
    DUE_PROMPT = "due_prompt"
    DUE_RESTORE = "due_restore"
    SHOWN = "shown"
    UNKNOWN_DELIVERY = "unknown_delivery"
    CONTINUE = "continue"
    CANCEL = "cancel"
    TIMEOUT = "timeout"
    FINISH = "finish"
    UNKNOWN_EFFECT = "unknown_effect"
    EXHAUSTED = "exhausted"


def reduce_phase(phase: Phase, trigger: Trigger) -> Phase:
    """Return the legal next phase, rejecting invalid stage interleavings."""
    if trigger is Trigger.CLEAR:
        return Phase.DISARMED
    if trigger is Trigger.EXHAUSTED:
        return Phase.QUARANTINED
    if trigger is Trigger.UNKNOWN_EFFECT:
        return Phase.EFFECT_UNKNOWN
    if trigger is Trigger.ENTER and phase in {
        Phase.DISARMED,
        Phase.ACTIVE,
        Phase.PROMPTED,
        Phase.DELIVERY_UNKNOWN,
    }:
        return Phase.ACTIVE
    if trigger is Trigger.TOUCH and phase in {
        Phase.ACTIVE,
        Phase.DISARMED,
        Phase.PROMPTED,
        Phase.DELIVERY_UNKNOWN,
    }:
        return Phase.ACTIVE
    transitions = {
        (Phase.ACTIVE, Trigger.DUE_PROMPT): Phase.PROMPT_PENDING,
        (Phase.ACTIVE, Trigger.DUE_RESTORE): Phase.RESTORING,
        (Phase.PROMPT_PENDING, Trigger.SHOWN): Phase.PROMPTED,
        (Phase.PROMPT_PENDING, Trigger.UNKNOWN_DELIVERY): Phase.DELIVERY_UNKNOWN,
        (Phase.PROMPTED, Trigger.CONTINUE): Phase.RESUMING,
        (Phase.DELIVERY_UNKNOWN, Trigger.CONTINUE): Phase.RESUMING,
        (Phase.PROMPTED, Trigger.CANCEL): Phase.ABANDONING,
        (Phase.DELIVERY_UNKNOWN, Trigger.CANCEL): Phase.ABANDONING,
        (Phase.PROMPTED, Trigger.TIMEOUT): Phase.ABANDONING,
        (Phase.RESUMING, Trigger.FINISH): Phase.ACTIVE,
        (Phase.ABANDONING, Trigger.FINISH): Phase.DISARMED,
        (Phase.RESTORING, Trigger.FINISH): Phase.DISARMED,
    }
    try:
        return transitions[phase, trigger]
    except KeyError as exc:
        raise ActivityConflict("invalid idle transition") from exc
