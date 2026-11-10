"""Strict versioned JSON envelopes for authoritative navigation bookkeeping."""

from __future__ import annotations

import heapq
import json
from typing import TypeVar, cast

from aiogram_coordination import ExternalSession

from ..codec import decode, encode
from ..engine import EngineName
from ..errors import ConfigurationError, SchemaUnsupported
from ..json import identifier
from ..models import (
    CommitResult,
    ConversationKey,
    NavigationToken,
    PreparedAction,
    RenderResult,
    VersionedSnapshot,
)
from .state import Conversation, Operation, TokenRecord, fingerprint
from .tokens import _binding  # pyright: ignore[reportPrivateUsage]

T = TypeVar("T")


def _map(value: object, names: set[str] | None = None) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SchemaUnsupported("Malformed Redis navigation envelope")
    result = cast(dict[str, object], value)
    if not all(type(name) is str for name in result) or (
        names is not None and set(result) != names
    ):
        raise SchemaUnsupported("Malformed Redis navigation fields")
    return result


def _typed(value: object, cls: type[T]) -> T:
    if type(value) is not cls:
        raise SchemaUnsupported("Malformed Redis navigation value")
    return cast(T, value)


def _optional(value: object, cls: type[T]) -> T | None:
    return None if value is None else _typed(value, cls)


def _token(entry: TokenRecord) -> dict[str, object]:
    return dict(
        token=entry.token,
        operation_id=entry.operation_id,
        fingerprint=entry.fingerprint,
        consumed_by=entry.consumed_by,
    )


def dumps(key: ConversationKey, record: Conversation, *, storage_format: int = 1) -> str:
    values: dict[str, object] = dict(
        key=key,
        version=record.version,
        current=record.current,
        pending_id=record.pending_id,
        operations={
            name: dict(
                fingerprint=entry.fingerprint,
                prepared=entry.prepared,
                status=entry.status,
                result=entry.result,
                retention_until=entry.retention_until,
                completion_fingerprint=entry.completion_fingerprint,
                token_receipts={
                    token: _token(value) for token, value in entry.token_receipts.items()
                },
            )
            for name, entry in record.operations.items()
        },
        tokens={name: _token(value) for name, value in record.tokens.items()},
    )
    if storage_format >= 2:
        binding = record.external_session
        values["external_session"] = (
            None
            if binding is None
            else {
                "session_id": binding.session_id,
                "revision": binding.revision,
                "absolute_expires_at": binding.absolute_expires_at,
            }
        )
    elif record.external_session is not None:
        raise ConfigurationError("External sessions require storage format 2")
    return encode(values, schema_version=storage_format)


def loads(raw: str, key: ConversationKey, *, engine: EngineName = "python") -> Conversation:
    try:
        decoded = decode(raw, engine=engine)
    except ConfigurationError as error:
        raise SchemaUnsupported("Malformed Redis navigation persistence") from error
    version = json.loads(raw)["schema_version"]
    names = {"key", "version", "current", "pending_id", "operations", "tokens"}
    data = _map(decoded, names | ({"external_session"} if version >= 2 else set()))
    if _typed(data["key"], ConversationKey) != key:
        raise SchemaUnsupported("Redis conversation identity mismatch")
    record = Conversation(
        _typed(data["version"], str),
        _optional(data["current"], VersionedSnapshot),
        _optional(data["pending_id"], str),
    )
    if version >= 2 and data["external_session"] is not None:
        binding = _map(data["external_session"], {"session_id", "revision", "absolute_expires_at"})
        try:
            record.external_session = ExternalSession(
                _typed(binding["session_id"], str),
                _typed(binding["revision"], str),
                _typed(binding["absolute_expires_at"], int),
            )
        except ValueError as error:
            raise SchemaUnsupported("Malformed external session binding") from error
    try:
        identifier(record.version, "version")
    except ValueError as error:
        raise SchemaUnsupported("Redis navigation version is invalid") from error

    def rendered(value: RenderResult) -> None:
        if any(message.chat_id != key.chat_id for message in value.messages):
            raise SchemaUnsupported("Redis rendering belongs to another conversation")

    if record.current is not None:
        rendered(record.current.snapshot.view)
    canonical: dict[str, TokenRecord] = {}

    def token(value: object) -> TokenRecord:
        fields = _map(value, {"token", "operation_id", "fingerprint", "consumed_by"})
        result = TokenRecord(
            _typed(fields["token"], NavigationToken),
            _typed(fields["operation_id"], str),
            _typed(fields["fingerprint"], str),
            _optional(fields["consumed_by"], str),
        )
        try:
            identifier(result.operation_id, "operation_id")
            if result.consumed_by is not None:
                identifier(result.consumed_by, "consumed_by")
        except ValueError as error:
            raise SchemaUnsupported("Redis token receipt identity is invalid") from error
        if result.token.key != key or result.fingerprint != _binding(result.token):
            raise SchemaUnsupported("Redis token conversation mismatch")
        old = canonical.setdefault(result.token.token, result)
        if old != result:
            raise SchemaUnsupported("Redis token receipts disagree")
        return old

    for name, value in _map(data["operations"]).items():
        fields = _map(
            value,
            {
                "fingerprint",
                "prepared",
                "status",
                "result",
                "retention_until",
                "completion_fingerprint",
                "token_receipts",
            },
        )
        status = fields["status"]
        if status not in ("prepared", "completed", "unknown", "failed"):
            raise SchemaUnsupported("Unsupported Redis operation status")
        operation = Operation(
            _typed(fields["fingerprint"], str),
            _optional(fields["prepared"], PreparedAction),
            status,
            _optional(fields["result"], CommitResult),
            _typed(fields["retention_until"], int),
            _optional(fields["completion_fingerprint"], str),
        )
        if operation.retention_until <= 0:
            raise SchemaUnsupported("Redis operation retention is invalid")
        if operation.prepared is None and (
            operation.status != "completed"
            or operation.fingerprint != operation.completion_fingerprint
        ):
            raise SchemaUnsupported("Redis state-only operation receipt is inconsistent")
        if operation.prepared is not None and (
            operation.prepared.expires_at <= operation.prepared.prepared_at
            or operation.prepared.key != key
            or operation.prepared.operation_id != name
        ):
            raise SchemaUnsupported("Redis prepared action identity mismatch")
        operation.token_receipts = {
            name: token(value) for name, value in _map(fields["token_receipts"]).items()
        }
        if operation.prepared is not None:
            if operation.prepared.rendered is not None:
                rendered(operation.prepared.rendered)
            for effect in operation.prepared.effects.values():
                if isinstance(effect.result, RenderResult):
                    rendered(effect.result)
        if operation.result is not None:
            rendered(operation.result.snapshot.view)
            if operation.result.duplicate:
                raise SchemaUnsupported("Redis stored completion is a transport retry result")
        if operation.prepared is not None and (
            operation.prepared.status != operation.status
            or operation.prepared.fingerprint != operation.fingerprint
            or fingerprint(operation.prepared.intent) != operation.fingerprint
        ):
            raise SchemaUnsupported("Redis action receipt invariants disagree")
        if operation.status == "completed" and (
            operation.result is None or operation.completion_fingerprint is None
        ):
            raise SchemaUnsupported("Redis completed operation lacks receipt")
        if operation.status != "completed" and operation.result is not None:
            raise SchemaUnsupported("Redis unfinished operation has completion receipt")
        if any(
            receipt_name != receipt.operation_id
            for receipt_name, receipt in operation.token_receipts.items()
        ):
            raise SchemaUnsupported("Redis control receipt index mismatch")
        if operation.status == "completed" and operation.prepared is not None:
            prepared, result = operation.prepared, operation.result
            assert result is not None
            if (
                prepared.rendered is None
                or result.snapshot.expires_at != prepared.expires_at
                or result.snapshot.session_id != prepared.session_id
                or result.snapshot.view.view_id != prepared.view_id
                or result.snapshot.node_id != prepared.node_id
                or fingerprint(result.snapshot.params) != fingerprint(prepared.params)
                or fingerprint(prepared.rendered) != fingerprint(result.snapshot.view)
            ):
                raise SchemaUnsupported("Redis completion receipt disagrees with its action")
        record.operations[name] = operation
    record.tokens = {name: token(value) for name, value in _map(data["tokens"]).items()}
    if any(name != value.token.token for name, value in record.tokens.items()):
        raise SchemaUnsupported("Redis token index mismatch")
    if record.pending_id is not None and record.pending_id not in record.operations:
        raise SchemaUnsupported("Redis pending action is absent")
    if record.pending_id is not None:
        pending = record.operations[record.pending_id]
        if pending.prepared is None or pending.status not in {"prepared", "unknown"}:
            raise SchemaUnsupported("Redis pending action is not unresolved")
    for name, entry in record.operations.items():
        if entry.status in {"prepared", "unknown"} and name != record.pending_id:
            raise SchemaUnsupported("Redis unresolved action lost its pending slot")
    if record.current is not None and record.current.version != record.version:
        raise SchemaUnsupported("Redis navigation version mismatch")
    record.expiry_heap = [
        (entry.retention_until, operation_id)
        for operation_id, entry in record.operations.items()
        if entry.status in {"completed", "failed"}
    ]
    heapq.heapify(record.expiry_heap)
    return record
