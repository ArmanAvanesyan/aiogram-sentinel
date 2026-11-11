"""Bounded in-process repository bookkeeping, never application business state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Literal, cast

from aiogram_coordination import ExternalSession

from ..engine import EngineName, native_core, require_engine
from ..models import (
    CommitResult,
    NavigationToken,
    PreparedAction,
    RenderResult,
    VersionedSnapshot,
    ViewState,
)


def _canonical(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ViewState) and value.render_status == "complete":
        value = RenderResult(
            value.view_id,
            value.messages,
            value.reply_keyboard_key,
            value.locale,
            value.reply_keyboard_locale,
        )
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _canonical(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(child)
            for key, child in cast(Mapping[object, object], value).items()
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(child) for child in cast(tuple[object, ...], value)]
    return value


def payload_size(value: object) -> int:
    return len(
        json.dumps(
            _canonical(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def fingerprint(value: object, *, engine: EngineName = "python") -> str:
    require_engine(engine)
    raw = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (
        native_core().fingerprint_canonical(raw)
        if engine == "rust"
        else hashlib.sha256(raw.encode()).hexdigest()
    )


@dataclass
class Operation:
    fingerprint: str
    prepared: PreparedAction | None
    status: Literal["prepared", "completed", "unknown", "failed"] = "prepared"
    result: CommitResult | None = None
    retention_until: int = 0
    completion_fingerprint: str | None = None
    token_receipts: dict[str, TokenRecord] = field(default_factory=lambda: dict[str, TokenRecord]())


@dataclass
class TokenRecord:
    token: NavigationToken
    operation_id: str
    fingerprint: str
    consumed_by: str | None = None


@dataclass
class Conversation:
    version: str
    expiry_heap: list[tuple[int, str]] = field(
        default_factory=lambda: list[tuple[int, str]](), kw_only=True
    )
    unloaded_operations: int = field(default=0, kw_only=True)
    host_session: tuple[str, int] | None = field(default=None, kw_only=True)
    views: dict[tuple[str, str], str] = field(
        default_factory=lambda: dict[tuple[str, str], str](), kw_only=True
    )
    external_session: ExternalSession | None = field(default=None, kw_only=True)
    current: VersionedSnapshot | None = None
    pending_id: str | None = None
    operations: dict[str, Operation] = field(default_factory=lambda: dict[str, Operation]())
    tokens: dict[str, TokenRecord] = field(default_factory=lambda: dict[str, TokenRecord]())
