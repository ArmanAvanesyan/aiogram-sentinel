"""Public bounded canonical-ledger projection for standalone and component hosts."""

from __future__ import annotations

import json
import math
from typing import cast

from ..clock import Clock
from ..config import NavigationConfig
from ..engine import strict_loads
from ..errors import SchemaUnsupported
from ..json import freeze_json, thaw_json
from ..models import ConversationKey
from .ledger import LedgerDelta, LedgerRead
from .memory import MemoryNavigationRepository
from .redis_codec import dumps, loads


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SchemaUnsupported("Malformed canonical ledger mapping")
    mapping = cast(dict[object, object], value)
    if any(type(key) is not str for key in mapping):
        raise SchemaUnsupported("Malformed canonical ledger mapping")
    return cast(dict[str, object], value)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class NavigationLedgerReducer:
    """Hydrate only selected operations; emit one atomic, bounded mutation.

    Hosts must include pending/current-control owner and requested/indexed operations
    in a read, and persist every delta together with their activity/deadline CAS.
    ``integration_payload`` is opaque first-result evidence owned by its Nav row.
    """

    def __init__(
        self, key: ConversationKey, read: LedgerRead, *, clock: Clock, config: NavigationConfig
    ) -> None:
        self.key, self.read, self.config = key, read, config
        self.repository = MemoryNavigationRepository(clock=clock, config=config)
        self.repository._storage_format = 3  # pyright: ignore[reportPrivateUsage]
        self._rows: dict[str, dict[str, object]] = {}
        self._integration: dict[str, object] = {}
        self._current_owner: object = None
        self._old_indexes: dict[str, tuple[str, ...]] = {}
        if read.hot is None:
            if read.operations or read.retained_count or read.revision is not None:
                raise SchemaUnsupported("Canonical ledger lost its hot state")
            return
        hot = _mapping(strict_loads(read.hot, engine=config.engine, max_bytes=8_388_608))
        if (
            set(hot) != {"schema_version", "kind", "core", "current_owner"}
            or hot["schema_version"] != 3
            or hot["kind"] != "hot"
        ):
            raise SchemaUnsupported("Malformed canonical hot state")
        self._current_owner = hot["current_owner"]
        root = _mapping(hot["core"])
        fields = _mapping(_mapping(root["value"])["value"])
        operation_fields = _mapping(_mapping(fields["operations"])["value"])
        if operation_fields:
            raise SchemaUnsupported("Hot state must not contain historical operation rows")
        for operation_id, raw in read.operations.items():
            row = _mapping(strict_loads(raw, engine=config.engine, max_bytes=8_388_608))
            if (
                set(row) != {"schema_version", "kind", "core", "integration_payload"}
                or row["schema_version"] != 3
                or row["kind"] != "operation"
            ):
                raise SchemaUnsupported("Malformed canonical operation row")
            self._rows[operation_id] = row
            self._integration[operation_id] = row["integration_payload"]
            core = _mapping(row["core"])
            body = _mapping(core["value"])
            expiry = read.operation_expiry.get(operation_id)
            if body["status"] in ("completed", "failed"):
                if expiry is None:
                    raise SchemaUnsupported("Terminal canonical receipt lost its expiry index")
                body["retention_until"] = expiry
                if expiry <= clock.now():
                    self._integration[operation_id] = None
            elif expiry is not None:
                raise SchemaUnsupported("Unresolved canonical receipt cannot expire")
            operation_fields[operation_id] = core
        record = loads(_json(root), key, engine=config.engine)
        if record.version != read.revision:
            raise SchemaUnsupported("Canonical ledger revision disagrees with hot state")
        self._old_indexes = {
            operation_id: tuple(
                field
                for token in entry.token_receipts.values()
                for field in (f"t:{token.token.token}", f"o:{token.operation_id}")
            )
            for operation_id, entry in record.operations.items()
        }
        record.unloaded_operations = read.retained_count - len(read.operations)
        self.repository._records[key] = record  # pyright: ignore[reportPrivateUsage]

    def set_integration_payload(self, operation_id: str, payload: object) -> None:
        # Caller supplies strict JSON only; serialization defensively validates it.
        frozen = json.loads(_json(thaw_json(freeze_json(payload))))
        previous = self._integration.get(operation_id)
        if previous is not None and previous != frozen:
            raise SchemaUnsupported("Canonical first integration result is immutable")
        self._integration[operation_id] = frozen

    def delta(self) -> LedgerDelta:
        record = self.repository._records.get(self.key)  # pyright: ignore[reportPrivateUsage]
        if record is None:
            return LedgerDelta(
                self.read.revision,
                self.read.revision or "absent",
                None,
                {},
                tuple(self.read.operations),
                {},
                {},
            )
        root = _mapping(json.loads(dumps(self.key, record, storage_format=3)))
        fields = _mapping(_mapping(root["value"])["value"])
        operations = _mapping(_mapping(fields["operations"])["value"])
        put: dict[str, str] = {}
        retention: dict[str, int] = {}
        indexes: dict[str, str] = {}
        for operation_id, core in operations.items():
            body = _mapping(_mapping(core)["value"])
            status = body["status"]
            old = self._rows.get(operation_id)
            old_status = _mapping(_mapping(old["core"])["value"])["status"] if old else None
            if status in ("completed", "failed"):
                body["retention_until"] = 1  # actual expiry is anchored by host COMMIT TIME
                if old_status not in ("completed", "failed"):
                    retention[operation_id] = math.ceil(self.config.recovery_seconds * 1000)
            row = dict(
                schema_version=3,
                kind="operation",
                core=core,
                integration_payload=self._integration.get(operation_id),
            )
            encoded = _json(row)
            if encoded != self.read.operations.get(operation_id):
                put[operation_id] = encoded
            entry = record.operations[operation_id]
            for receipt in entry.token_receipts.values():
                indexes[f"t:{receipt.token.token}"] = operation_id
                indexes[f"o:{receipt.operation_id}"] = operation_id
        operations.clear()
        current_owner = self._current_owner
        if record.current is not None:
            current_view = record.current.snapshot.view.view_id
            for operation_id, entry in record.operations.items():
                if entry.prepared is not None and entry.prepared.view_id == current_view:
                    current_owner = operation_id
                    break
            else:
                current_owner = None
        hot = _json(dict(schema_version=3, kind="hot", core=root, current_owner=current_owner))
        removed = set(self.read.operations) - record.operations.keys()
        deleted_indexes = tuple(
            field
            for operation_id in removed
            for field in self._old_indexes.get(operation_id, ())
            if field not in indexes
        )
        return LedgerDelta(
            self.read.revision,
            record.version,
            hot,
            put,
            tuple(removed),
            retention,
            indexes,
            deleted_indexes,
        )
