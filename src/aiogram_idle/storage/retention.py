"""Retention admission protects unfinished effects and live claim owners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from ..models import Phase, RuntimeSnapshot
from .state import Job

PENDING_PHASES = frozenset(
    {
        Phase.PROMPT_PENDING,
        Phase.RESUMING,
        Phase.ABANDONING,
        Phase.RESTORING,
    }
)


def may_prune(record: RuntimeSnapshot, job: Job | None, now: float) -> bool:
    marker = record.components.get("__idle_owner__")
    if isinstance(marker, Mapping) and (
        marker.get("pending") is True or cast(float, marker.get("retain_until", 0)) > now
    ):
        return False
    if record.session.expires_at > now or record.recovery_until > now:
        return False
    if job is not None and job.token is not None and job.lease_until > now:
        return False
    # A worker must explicitly resolve or quarantine pending effects before
    # retention may discard their only recovery evidence.
    return record.idle.operation is None or record.idle.phase not in PENDING_PHASES


def ensure_activity_mutable(record: RuntimeSnapshot) -> None:
    """Public acceptance cannot erase an operation's external-effect ledger."""
    from ..errors import ActivityConflict

    if "__idle_owner__" in record.components:
        raise ActivityConflict("An integration owns the activity slot; use its guarded writer")
    if record.idle.operation is not None and record.idle.phase in PENDING_PHASES | {
        Phase.ACTIVE,
        Phase.EFFECT_UNKNOWN,
        Phase.QUARANTINED,
    }:
        raise ActivityConflict("A reserved idle operation must complete or be recovered first")
