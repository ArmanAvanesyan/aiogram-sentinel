"""Memory-only storage metadata; never contains application callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from ..models import IdleConversationKey

T = TypeVar("T")


@dataclass(frozen=True)
class Claim:
    key: IdleConversationKey
    token: str
    generation: int
    lease_until: float
    deadline: float


@dataclass(frozen=True)
class ControlToken:
    key: IdleConversationKey
    token: str
    prompt_id: str
    session_id: str
    activity_id: str
    expires_at: float


@dataclass(frozen=True)
class OperationReceipt(Generic[T]):
    fingerprint: str
    result: T
    expires_at: float


@dataclass
class Job:
    generation: int
    deadline: float
    eligible_at: float
    token: str | None = None
    lease_until: float = 0


@dataclass(frozen=True)
class OperationLookup:
    status: Literal["found", "not_found_within_retention", "unknown_history"]
    result: object | None = None
