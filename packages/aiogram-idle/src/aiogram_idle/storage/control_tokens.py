"""Bounded token ownership checks, called under the backend's atomic lock."""

from __future__ import annotations

from ..errors import ActivityConflict, Overloaded
from ..models import RuntimeSnapshot
from .state import ControlToken


def reserve(
    record: RuntimeSnapshot,
    tokens: dict[str, ControlToken],
    *,
    token: str,
    prompt_id: str,
    activity_id: str,
    expires_at: float,
    now: float,
    limit: int,
) -> ControlToken:
    if record.activity is None or record.activity.activity_id != activity_id:
        raise ActivityConflict("The activity generation changed")
    for previous, value in tuple(tokens.items()):
        if (
            value.expires_at <= now
            or value.session_id != record.session.session_id
            or value.activity_id != activity_id
            or value.prompt_id != prompt_id
        ):
            del tokens[previous]
    value = ControlToken(
        record.key, token, prompt_id, record.session.session_id, activity_id, expires_at
    )
    old = tokens.get(token)
    if old is not None:
        if old != value:
            raise ActivityConflict("Control token already belongs to another prompt")
        return old
    if len(tokens) >= limit:
        raise Overloaded("Control token capacity is exhausted")
    if not token or len(token) > 64 or expires_at <= now:
        raise ValueError("Invalid control token or expiry")
    tokens[token] = value
    return value


def resolve(
    record: RuntimeSnapshot | None, token: ControlToken | None, *, now: float
) -> ControlToken | None:
    if (
        record is None
        or token is None
        or token.expires_at <= now
        or record.session.expires_at <= now
        or record.session.session_id != token.session_id
        or record.activity is None
        or record.activity.activity_id != token.activity_id
        or record.activity.expires_at <= now
    ):
        return None
    return token
