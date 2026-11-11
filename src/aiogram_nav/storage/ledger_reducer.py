"""Public bounded canonical-ledger projection for standalone and component hosts."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from ..clock import Clock
from ..codec import encode
from ..config import NavigationConfig
from ..engine import strict_loads
from ..errors import OperationIdConflict, Overloaded, SchemaUnsupported, SessionExpired
from ..json import freeze_json, identifier, thaw_json, timestamp_ms
from ..models import ConversationKey
from .ledger import LedgerDelta, LedgerRead, view_index
from .memory import MemoryNavigationRepository
from .redis_codec import dumps, loads
from .state import Conversation as NavigationLedgerRecord


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SchemaUnsupported("Malformed canonical ledger mapping")
    mapping = cast(dict[object, object], value)
    if any(type(key) is not str for key in mapping):
        raise SchemaUnsupported("Malformed canonical ledger mapping")
    return cast(dict[str, object], value)


def _parse(raw: str, config: NavigationConfig) -> object:
    try:
        return strict_loads(raw, engine=config.engine, max_bytes=8_388_608)
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise SchemaUnsupported("Malformed canonical ledger JSON") from error


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class NavigationLedgerReducer:
    """Hydrate only selected operations; emit one atomic, bounded mutation.

    Hosts must include pending/current-control owner and requested/indexed operations
    in a read, and persist every delta together with their activity/deadline CAS.
    ``integration_payload`` is opaque first-result evidence owned by its Nav row.
    """

    def __init__(
        self,
        key: ConversationKey,
        read: LedgerRead,
        *,
        clock: Clock,
        config: NavigationConfig,
        required_indexes: Sequence[str] = (),
    ) -> None:
        if any(field not in read.indexes for field in required_indexes):
            raise SchemaUnsupported("Host omitted a required canonical index lookup proof")
        if len(read.operations) > 40:
            raise SchemaUnsupported("Canonical reads must be bounded projections, not full history")
        self.key, self.read, self.config = key, read, config
        self._externally_exposed = False
        self.repository = MemoryNavigationRepository(clock=clock, config=config)
        self.repository._storage_format = 3  # pyright: ignore[reportPrivateUsage]
        self._rows: dict[str, dict[str, object]] = {}
        self._terminal_core: dict[str, str] = {}
        self._integration: dict[str, object] = {}
        self._current_owner: object = None
        self._old_indexes: dict[str, tuple[str, ...]] = {}
        if read.hot is None:
            if (
                read.operations
                or read.retained_count
                or read.revision is not None
                or any(value is not None for value in read.indexes.values())
            ):
                raise SchemaUnsupported("Canonical ledger lost its hot state")
            return
        hot = _mapping(_parse(read.hot, config))
        if (
            set(hot)
            != {
                "schema_version",
                "kind",
                "core",
                "current_owner",
                "revision",
                "pending_id",
                "session_id",
            }
            or hot["schema_version"] != 3
            or hot["kind"] != "hot"
        ):
            raise SchemaUnsupported("Malformed canonical hot state")
        self._current_owner = hot["current_owner"]
        if hot["revision"] != read.revision:
            raise SchemaUnsupported("Canonical hot revision mismatch")
        root = _mapping(hot["core"])
        if set(root) != {"schema_version", "value"} or root["schema_version"] != 3:
            raise SchemaUnsupported("Malformed canonical core envelope")
        wrapped = _mapping(root["value"])
        if set(wrapped) != {"type", "value"} or wrapped["type"] != "mapping":
            raise SchemaUnsupported("Malformed canonical core mapping")
        fields = _mapping(wrapped["value"])
        operations = _mapping(fields.get("operations"))
        if set(operations) != {"type", "value"} or operations["type"] != "mapping":
            raise SchemaUnsupported("Malformed canonical operation projection")
        operation_fields = _mapping(operations["value"])
        if operation_fields:
            raise SchemaUnsupported("Hot state must not contain historical operation rows")
        for operation_id, raw in read.operations.items():
            row = _mapping(_parse(raw, config))
            if (
                set(row)
                != {
                    "schema_version",
                    "kind",
                    "id",
                    "status",
                    "conversation",
                    "core",
                    "integration_payload",
                }
                or row["schema_version"] != 3
                or row["kind"] != "operation"
            ):
                raise SchemaUnsupported("Malformed canonical operation row")
            if row.get("id") != operation_id or row.get("conversation") != encode(key):
                raise SchemaUnsupported("Canonical operation identity mismatch")
            if row.get("status") in ("completed", "failed"):
                invariant = dict(_mapping(_mapping(row["core"])["value"]))
                invariant.pop("token_receipts", None)
                self._terminal_core[operation_id] = json.dumps(
                    invariant,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            self._rows[operation_id] = row
            self._integration[operation_id] = row["integration_payload"]
            core = _mapping(row["core"])
            if set(core) != {"type", "value"} or core["type"] != "mapping":
                raise SchemaUnsupported("Malformed canonical operation core")
            body = _mapping(core["value"])
            if row.get("status") != body.get("status"):
                raise SchemaUnsupported("Canonical operation status mismatch")
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
        record = loads(
            _json(root), key, engine=config.engine, max_bytes=8_388_608 * (len(read.operations) + 1)
        )
        if record.pending_id != hot["pending_id"]:
            raise SchemaUnsupported("Canonical pending reference mismatch")
        if record.version != read.revision:
            raise SchemaUnsupported("Canonical ledger revision disagrees with hot state")
        if self._current_owner is not None and self._current_owner not in read.expired:
            if type(self._current_owner) is not str:
                raise SchemaUnsupported("Canonical current owner is malformed")
            owner = record.operations.get(self._current_owner)
            if (
                owner is None
                or owner.prepared is None
                or record.current is None
                or owner.prepared.view_id != record.current.snapshot.view.view_id
                or owner.prepared.session_id != record.current.snapshot.session_id
            ):
                raise SchemaUnsupported("Canonical current owner disagrees with its active view")
        for index, owner_id in read.indexes.items():
            if owner_id is None or owner_id in read.expired:
                continue
            owner = record.operations.get(owner_id)
            if owner is None:
                raise SchemaUnsupported("Canonical index owner is not retained")
            if index.startswith("v:"):
                valid = (
                    owner.prepared is not None
                    and view_index(owner.prepared.view_id, owner.prepared.session_id) == index
                )
            elif index.startswith("t:"):
                valid = any(
                    token.token.token == index[2:] for token in owner.token_receipts.values()
                )
            elif index.startswith("o:"):
                valid = any(
                    token.operation_id == index[2:] for token in owner.token_receipts.values()
                )
            else:
                valid = False
            if not valid:
                raise SchemaUnsupported("Canonical index proof disagrees with its owner")
        if (
            record.host_session is not None
            and record.current is not None
            and record.current.snapshot.expires_at > clock.now()
            and record.current.snapshot.session_id != record.host_session[0]
        ):
            raise SchemaUnsupported("Live navigation disagrees with its host generation")
        pending = record.operations.get(record.pending_id) if record.pending_id else None
        expected_session = (
            record.host_session[0]
            if record.host_session is not None
            else record.current.snapshot.session_id
            if record.current is not None
            else pending.prepared.session_id
            if pending is not None and pending.prepared is not None
            else None
        )
        if hot["session_id"] != expected_session:
            raise SchemaUnsupported("Canonical hot session disagrees with authoritative state")
        self._old_indexes = {
            operation_id: (
                (view_index(entry.prepared.view_id, entry.prepared.session_id),)
                if entry.prepared is not None
                else ()
            )
            + tuple(
                field
                for token in entry.token_receipts.values()
                for field in (f"t:{token.token.token}", f"o:{token.operation_id}")
            )
            for operation_id, entry in record.operations.items()
        }
        record.unloaded_operations = (
            read.retained_count
            - len(read.operations)
            - len(set(read.expired) - read.operations.keys())
        )
        self.repository._records[key] = record  # pyright: ignore[reportPrivateUsage]

    view_index = staticmethod(view_index)

    @property
    def session_id(self) -> str | None:
        record = self.repository._records.get(self.key)  # pyright: ignore[reportPrivateUsage]
        if record is None:
            return None
        if record.host_session is not None:
            return record.host_session[0]
        if record.current is not None:
            return record.current.snapshot.session_id
        pending = record.operations.get(record.pending_id) if record.pending_id else None
        return (
            pending.prepared.session_id
            if pending is not None and pending.prepared is not None
            else None
        )

    def bind_session_generation(self, session_id: str, expires_at: datetime | int) -> None:
        """Bind a verified host generation before prepare or scoped index selection.

        This pure hook does not authenticate its caller. The owning host must verify
        its session authority and fence the eventual atomic component commit.
        Existing generation deadlines are immutable, including expired deadlines.
        """
        identifier(session_id, "host session_id")
        cap = timestamp_ms(expires_at)
        now = self.repository.clock.now()
        if cap <= now:
            raise SessionExpired("Authoritative host generation expired")
        record = self.repository._admit(self.key)  # pyright: ignore[reportPrivateUsage]
        candidates: list[int] = []
        if record.host_session is not None and record.host_session[0] == session_id:
            candidates.append(record.host_session[1])
        current = record.current.snapshot if record.current is not None else None
        if current is not None:
            if current.session_id == session_id:
                candidates.append(current.expires_at)
            elif current.expires_at > now:
                raise SessionExpired("Live navigation belongs to another host generation")
        pending = record.operations.get(record.pending_id) if record.pending_id else None
        if pending is not None:
            if pending.prepared is None or pending.prepared.session_id != session_id:
                raise SessionExpired("Pending render belongs to another host generation")
            candidates.append(pending.prepared.expires_at)
        if candidates and (len(set(candidates)) != 1 or candidates[0] > cap):
            raise SessionExpired("Authoritative host generation expiry is immutable")
        effective = candidates[0] if candidates else cap
        if effective <= now:
            raise SessionExpired("Expired navigation generation must be replaced explicitly")
        record.host_session = (session_id, effective)

    @property
    def record(self) -> NavigationLedgerRecord | None:
        """Owned transient projection; never an authoritative shared store object."""
        self._externally_exposed = True
        return self.repository._records.get(self.key)  # pyright: ignore[reportPrivateUsage]

    def replace_record(self, record: NavigationLedgerRecord | None) -> None:
        """Install a validated pure-normalizer result before generating its delta."""
        if record is None:
            self.repository._records.pop(self.key, None)  # pyright: ignore[reportPrivateUsage]
            return
        # Detach the accepted normalizer result so later caller mutations cannot
        # alter what this reducer will commit.
        validated = loads(
            dumps(
                self.key,
                record,
                storage_format=3,
                max_bytes=8_388_608 * (len(record.operations) + 1),
            ),
            self.key,
            engine=self.config.engine,
            max_bytes=8_388_608 * (len(record.operations) + 1),
        )
        validated.unloaded_operations = record.unloaded_operations
        self.repository._records[self.key] = validated  # pyright: ignore[reportPrivateUsage]
        self._externally_exposed = False

    @classmethod
    def from_legacy(
        cls, key: ConversationKey, raw: str, *, clock: Clock, config: NavigationConfig
    ) -> NavigationLedgerReducer:
        """Pure one-time conversion; caller must commit under an activated fence.

        This never performs I/O or effects. Terminal absolute deadlines are available
        through ``legacy_expiry`` and must be preserved by the migration transaction.
        """
        projection = cls(key, LedgerRead(None, None, {}, 0, {}), clock=clock, config=config)
        record = loads(raw, key, engine=config.engine)
        projection.repository._prune(record)  # pyright: ignore[reportPrivateUsage]
        projection.repository._records[key] = record  # pyright: ignore[reportPrivateUsage]
        return projection

    @property
    def legacy_expiry(self) -> dict[str, int]:
        record = self.repository._records.get(self.key)  # pyright: ignore[reportPrivateUsage]
        return (
            {}
            if record is None
            else {
                operation_id: entry.retention_until
                for operation_id, entry in record.operations.items()
                if entry.status in ("completed", "failed")
            }
        )

    def integration_payload(self, operation_id: str) -> object | None:
        """Return a detached first accepted integration result, never current state."""
        value = self._integration.get(operation_id)
        return None if value is None else json.loads(_json(value))

    def set_integration_payload(self, operation_id: str, payload: object) -> None:
        record = self.repository._records.get(self.key)  # pyright: ignore[reportPrivateUsage]
        if record is None or operation_id not in record.operations:
            raise SchemaUnsupported("Canonical operation must exist before its integration result")
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
                tuple(set(self.read.operations) | set(self.read.expired)),
                {},
                {},
            )
        encoded_core = dumps(
            self.key, record, storage_format=3, max_bytes=8_388_608 * (len(record.operations) + 1)
        )
        if self._externally_exposed:
            loads(
                encoded_core,
                self.key,
                engine=self.config.engine,
                max_bytes=8_388_608 * (len(record.operations) + 1),
            )
            self._externally_exposed = False
        root = _mapping(json.loads(encoded_core))
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
            if operation_id in self._terminal_core:
                invariant = dict(body)
                invariant.pop("token_receipts", None)
                if (
                    json.dumps(
                        invariant,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                    != self._terminal_core[operation_id]
                ):
                    raise OperationIdConflict("A retained canonical terminal result is immutable")
            row = dict(
                schema_version=3,
                kind="operation",
                id=operation_id,
                status=status,
                conversation=encode(self.key),
                core=core,
                integration_payload=self._integration.get(operation_id),
            )
            encoded = _json(row)
            if len(encoded.encode()) > 8_388_608:
                raise Overloaded("Canonical operation row exceeds its configured persistence bound")
            if encoded != self.read.operations.get(operation_id):
                put[operation_id] = encoded
            entry = record.operations[operation_id]
            if entry.prepared is not None:
                indexes[view_index(entry.prepared.view_id, entry.prepared.session_id)] = (
                    operation_id
                )
            for receipt in entry.token_receipts.values():
                indexes[f"t:{receipt.token.token}"] = operation_id
                indexes[f"o:{receipt.operation_id}"] = operation_id
        operations.clear()
        current_owner = self._current_owner if record.current is not None else None
        if record.current is not None:
            current_view = record.current.snapshot.view.view_id
            for operation_id, entry in record.operations.items():
                if (
                    entry.prepared is not None
                    and entry.prepared.view_id == current_view
                    and entry.prepared.session_id == record.current.snapshot.session_id
                ):
                    current_owner = operation_id
                    break
            else:
                current_owner = None
        hot = _json(
            dict(
                schema_version=3,
                kind="hot",
                revision=record.version,
                pending_id=record.pending_id,
                session_id=self.session_id,
                core=root,
                current_owner=current_owner,
            )
        )
        if len(hot.encode()) > 8_388_608:
            raise Overloaded("Canonical hot state exceeds its persistence bound")
        removed = (set(self.read.operations) - record.operations.keys()) | set(self.read.expired)
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
