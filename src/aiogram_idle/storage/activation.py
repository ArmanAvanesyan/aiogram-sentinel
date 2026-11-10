"""Fenced namespace activation and bounded, effect-free record migration."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..errors import (
    BackendInconsistent,
    ConfigurationMismatch,
    OperationIdConflict,
    VersionConflict,
)
from ..models import RuntimeSnapshot
from .codec import decode
from .format import StorageActivation, validate_activation
from .redis_engine import Engine, job_decode
from .redis_transport import array, text

if TYPE_CHECKING:
    from .redis_store import RedisStore

_ACTIVATE = """
local previous=redis.call('GET',KEYS[1]) or ''
if previous~=ARGV[1] then return 'conflict' end
if (redis.call('GET',KEYS[2]) or '')~=ARGV[2] then return 'conflict' end
if redis.call('SCARD',KEYS[3])~=tonumber(ARGV[5]) then return 'conflict' end
local tm=redis.call('TIME'); local now=tonumber(tm[1])+tonumber(tm[2])/1000000
for i=4,#KEYS do
 local raw=redis.call('GET',KEYS[i]); if raw then
  local job=cjson.decode(raw)
  if job.token and job.token~=cjson.null and job.lease_until>now then return 'active' end
 end
end
redis.call('SET',KEYS[2],ARGV[3]); redis.call('SET',KEYS[1],ARGV[4]); return 'ok'
"""


@dataclass(frozen=True)
class StorageMigrationPage:
    cursor: str
    inspected: int
    migrated: int
    dry_run: bool


async def format_manifest(store: RedisStore) -> tuple[int, dict[str, object] | None, str]:
    raw = await store.connection.call("GET", store.prefix + ":storage-format")
    if raw is None:
        return 1, None, ""
    encoded = text(raw)

    def unique(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Repeated storage format field")
            result[key] = value
        return result

    try:
        value: object = json.loads(encoded, object_pairs_hook=unique)
    except (TypeError, ValueError) as error:
        raise BackendInconsistent("Malformed storage format marker") from error
    if not isinstance(value, dict):
        raise BackendInconsistent("Malformed storage format marker")
    manifest = cast(dict[str, object], value)
    if (
        set(manifest) != {"format", "operation_id", "previous_history", "history"}
        or type(manifest["format"]) is not int
        or manifest["format"] != 2
        or any(
            not isinstance(manifest[name], str) or not manifest[name]
            for name in ("operation_id", "previous_history", "history")
        )
    ):
        raise BackendInconsistent("Unsupported storage format marker")
    return 2, manifest, encoded


async def activate(
    store: RedisStore,
    *,
    expected: int,
    target: int,
    operation_id: str,
    old_workers_drained: bool,
    dry_run: bool,
    active_scopes: int,
) -> StorageActivation:
    validate_activation(
        expected=expected,
        target=target,
        operation_id=operation_id,
        old_workers_drained=old_workers_drained,
        dry_run=dry_run,
    )
    version, manifest, encoded = await format_manifest(store)
    if manifest is not None:
        if manifest["operation_id"] != operation_id:
            raise OperationIdConflict("Storage format was activated by another operation")
        store.history = cast(str, manifest["history"])
        store.format_version = 2
        await store.ready()
        return StorageActivation(expected, target, False, dry_run)
    await store.ready()
    if version != expected:
        raise ConfigurationMismatch("Storage format changed before activation")
    members: list[object] = []
    cursor = "0"
    while True:
        page = array(
            await store.connection.call("SSCAN", store.prefix + ":live", cursor, "COUNT", 100)
        )
        cursor = text(page[0]) if not isinstance(page[0], int) else str(page[0])
        members.extend(array(page[1]))
        if cursor == "0":
            break
    jobs: set[str] = set()
    active = unresolved = 0
    for member in members:
        key = decode(text(member))
        from ..models import IdleConversationKey

        if not isinstance(key, IdleConversationKey):
            raise BackendInconsistent("Malformed retained identity during activation")
        engine, _, _ = await store.read(key)
        record = await engine.load(key)
        unresolved += int(record is not None and record.idle.operation is not None)
        job_key = store.keys(key)[1]
        jobs.add(job_key)
        raw_job = await store.connection.call("GET", job_key)
        if raw_job is not None:
            job = job_decode(text(raw_job))
            active += int(job.token is not None and job.lease_until > store.clock.now())
    report = StorageActivation(
        expected, target, not dry_run, dry_run, len(jobs), active, unresolved
    )
    if dry_run:
        return report
    if active or active_scopes:
        raise ConfigurationMismatch("Protected work must drain before activation")
    old_history = store.history
    history = old_history.split(":", 1)[0] + ":" + store.storage_profile(version=2)
    body = json.dumps(
        {
            "format": 2,
            "operation_id": operation_id,
            "previous_history": old_history,
            "history": history,
        },
        sort_keys=True,
    )
    result = text(
        await store.connection.script(
            _ACTIVATE,
            [
                store.prefix + ":created",
                store.prefix + ":storage-format",
                store.prefix + ":live",
                *sorted(jobs),
            ],
            [old_history, encoded, body, history, len(jobs)],
        )
    )
    if result == "active":
        raise ConfigurationMismatch("A deadline claim became active during activation")
    if result != "ok":
        raise VersionConflict("Namespace changed during storage activation")
    store.format_version = 2
    store.history = history
    return report


async def migrate_records(
    store: RedisStore, *, cursor: str = "0", limit: int = 100, dry_run: bool = True
) -> StorageMigrationPage:
    if not isinstance(cast(object, cursor), str) or len(cursor) > 8_388_608:
        raise ValueError("Malformed or oversized migration cursor")
    if type(limit) is not int or not 1 <= limit <= 1000 or type(dry_run) is not bool:
        raise ValueError("Migration limit must be between 1 and 1000")
    await store.ready()
    if store.format_version != 2 and not dry_run:
        raise ConfigurationMismatch("Activate storage format 2 before migrating records")
    escaped = "".join(
        "\\" + character if character in "\\*?[]" else character for character in store.prefix
    )

    pending: list[object] = []
    scan_cursor = cursor
    if cursor.startswith("page:"):
        try:
            state = json.loads(base64.urlsafe_b64decode(cursor[5:].encode()))
            scan_cursor, pending = state["cursor"], state["pending"]
            if (
                not isinstance(scan_cursor, str)
                or not scan_cursor.isdecimal()
                or not isinstance(cast(object, pending), list)
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError("Malformed migration cursor") from error
    if not scan_cursor.isdecimal():
        raise ValueError("Malformed migration cursor")
    if not pending:
        page = array(
            await store.connection.call(
                "SCAN",
                scan_cursor,
                "MATCH",
                escaped + ":record:*",
                "COUNT",
                limit,
            )
        )
        scan_cursor = str(page[0]) if isinstance(page[0], int) else text(page[0])
        pending = array(page[1])
    selected, pending = pending[:limit], pending[limit:]
    inspected = migrated = 0
    for name in selected:
        if not text(name).startswith(store.prefix + ":record:"):
            raise ValueError("Migration cursor belongs to another namespace")
        raw = await store.connection.call("GET", name)
        if raw is None:
            continue
        payload = decode(text(raw))
        if not isinstance(payload, dict):
            raise BackendInconsistent("Malformed migration record")
        record = cast(dict[str, object], payload).get("record")
        if not isinstance(record, RuntimeSnapshot) or store.keys(record.key)[0] != text(name):
            raise BackendInconsistent("Migration record identity mismatch")
        inspected += 1
        if json.loads(text(raw))["schema_version"] == 2:
            continue
        if not dry_run:

            async def retain(engine: Engine) -> None:
                return None

            await store.mutate(record.key, retain)
            migrated += 1
    result_cursor = scan_cursor
    if pending:
        payload = json.dumps({"cursor": scan_cursor, "pending": [text(value) for value in pending]})
        result_cursor = "page:" + base64.urlsafe_b64encode(payload.encode()).decode()
    return StorageMigrationPage(result_cursor, inspected, migrated, dry_run)
