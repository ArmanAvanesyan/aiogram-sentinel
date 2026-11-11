"""Opaque canonical-ledger wire contract shared with optional component hosts.

A host persists these rows without importing navigation. Only the navigation codec
interprets the row bodies. Every delta commits with the host activity/deadline CAS;
no second acknowledgement or duplicate historical snapshot is retained by a host.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import cast

from ..errors import ConfigurationError
from ..json import identifier


def _strings(values: Mapping[str, str]) -> Mapping[str, str]:
    if any(
        type(key) is not str or not key or type(value) is not str for key, value in values.items()
    ):
        raise ConfigurationError("Canonical ledger fields must be named strings")
    return MappingProxyType(dict(values))


def view_index(view_id: str, session_id: str) -> str:
    identifier(view_id, "view_id")
    identifier(session_id, "session_id")
    raw = json.dumps([session_id, view_id], ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return "v:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class LedgerRead:
    revision: str | None
    hot: str | None
    operations: Mapping[str, str]
    retained_count: int
    operation_expiry: Mapping[str, int]
    expired: tuple[str, ...] = ()
    indexes: Mapping[str, str | None] = field(
        default_factory=lambda: dict[str, str | None](), kw_only=True
    )

    def __post_init__(self) -> None:
        if type(self.retained_count) is not int or self.retained_count < len(self.operations):
            raise ConfigurationError("Canonical ledger count is inconsistent")
        object.__setattr__(self, "operations", _strings(self.operations))
        if any(type(value) is not int or value < 0 for value in self.operation_expiry.values()):
            raise ConfigurationError("Canonical operation expiry must be epoch milliseconds")
        object.__setattr__(self, "operation_expiry", MappingProxyType(dict(self.operation_expiry)))
        object.__setattr__(self, "expired", tuple(self.expired))
        if any(
            type(key) is not str or (value is not None and (type(value) is not str or not value))
            for key, value in self.indexes.items()
        ):
            raise ConfigurationError("Canonical index proofs must name their optional owner")
        object.__setattr__(self, "indexes", MappingProxyType(dict(self.indexes)))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> LedgerRead:
        expected = {
            "revision",
            "hot",
            "operations",
            "retained_count",
            "operation_expiry",
            "expired",
        }
        if set(payload) - {"indexes"} != expected:
            raise ConfigurationError("Canonical ledger read has unsupported fields")
        for name in ("revision", "hot"):
            if payload[name] is not None and type(payload[name]) is not str:
                raise ConfigurationError("Canonical ledger read metadata is malformed")
        if not isinstance(payload["operations"], Mapping) or not isinstance(
            payload["operation_expiry"], Mapping
        ):
            raise ConfigurationError("Canonical ledger read indexes must be mappings")
        if not isinstance(payload.get("indexes", {}), Mapping):
            raise ConfigurationError("Canonical ledger lookup proofs must be a mapping")
        expired = payload["expired"]
        if not isinstance(expired, (tuple, list)) or any(
            type(item) is not str for item in cast(tuple[object, ...], expired)
        ):
            raise ConfigurationError("Canonical ledger expiry page is malformed")
        return cls(
            cast(str | None, payload["revision"]),
            cast(str | None, payload["hot"]),
            cast(Mapping[str, str], payload["operations"]),
            cast(int, payload["retained_count"]),
            cast(Mapping[str, int], payload["operation_expiry"]),
            tuple(cast(tuple[str, ...], expired)),
            indexes=cast(Mapping[str, str | None], payload.get("indexes", {})),
        )

    def to_payload(self) -> dict[str, object]:
        return dict(
            revision=self.revision,
            hot=self.hot,
            operations=dict(self.operations),
            retained_count=self.retained_count,
            operation_expiry=dict(self.operation_expiry),
            expired=list(self.expired),
            indexes=dict(self.indexes),
        )


@dataclass(frozen=True)
class LedgerDelta:
    expected_revision: str | None
    revision: str
    hot: str | None
    put: Mapping[str, str]
    delete: tuple[str, ...]
    terminal_retention_ms: Mapping[str, int]
    token_index_put: Mapping[str, str]
    token_index_delete: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.revision) is not str or not self.revision:
            raise ConfigurationError("Canonical ledger revision is required")
        object.__setattr__(self, "put", _strings(self.put))
        object.__setattr__(self, "token_index_put", _strings(self.token_index_put))
        if any(
            type(value) is not int or value <= 0 for value in self.terminal_retention_ms.values()
        ):
            raise ConfigurationError("Terminal retention must be positive milliseconds")
        if not self.terminal_retention_ms.keys() <= self.put.keys():
            raise ConfigurationError("Terminal retention requires its canonical row")
        object.__setattr__(
            self, "terminal_retention_ms", MappingProxyType(dict(self.terminal_retention_ms))
        )
        object.__setattr__(self, "delete", tuple(self.delete))
        object.__setattr__(self, "token_index_delete", tuple(self.token_index_delete))

    def to_payload(self) -> dict[str, object]:
        return {
            "expected_revision": self.expected_revision,
            "revision": self.revision,
            "hot": self.hot,
            "put": dict(self.put),
            "delete": list(self.delete),
            "terminal_retention_ms": dict(self.terminal_retention_ms),
            "token_index_put": dict(self.token_index_put),
            "token_index_delete": list(self.token_index_delete),
        }
