"""Explicit namespace-format activation; records migrate only on normal CAS writes."""

from __future__ import annotations

# Namespace bookkeeping deliberately uses the store's internal transaction API.
# pyright: reportPrivateUsage=false
import json
import secrets
from typing import TYPE_CHECKING, cast

from ..codec import decode, encode
from ..errors import ConfigurationError, OperationIdConflict, PersistenceUnavailable
from ..json import identifier
from .redis_codec import loads
from .redis_scripts import READ, SCAN_PAGE
from .redis_transport import array, text
from .sessions import StorageMigrationReport

if TYPE_CHECKING:
    from .redis_store import RedisStore

ACTIVATE = """
local existing = redis.call('GET', KEYS[4])
if existing and existing ~= ARGV[6] then return {'existing', existing} end
if not existing and ARGV[6] ~= '' then return {'history'} end
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2] then
 return {'history'}
end
if redis.call('SISMEMBER', KEYS[3], '!established') ~= 1 then return {'history'} end
redis.call('SET', KEYS[1], ARGV[3])
redis.call('SET', KEYS[2], ARGV[4])
redis.call('SET', KEYS[4], ARGV[5])
return {'ok', ARGV[5]}
"""

_VALIDATE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2]
 or redis.call('GET', KEYS[4]) ~= ARGV[3] then return 0 end
if redis.call('SISMEMBER', KEYS[3], '!established') ~= 1 then return 0 end
return 1
"""


def _key(store: RedisStore) -> str:
    return f"{store.prefix}:storage-format"


def _profile(store: RedisStore, version: int = 2) -> str:
    return encode({"storage_format": version, "base_profile": decode(store.base_profile)})


def _manifest(raw: object, store: RedisStore) -> dict[str, object]:
    try:
        value: object = json.loads(text(raw))
        if not isinstance(value, dict):
            raise ValueError
        item = cast(dict[str, object], value)
        if set(item) != {
            "format",
            "operation_id",
            "previous_history",
            "history",
            "base_profile",
        } | ({"previous_manifest"} if item.get("format") == 3 else set()):
            raise ValueError
        if type(item["format"]) is not int or item["format"] not in (2, 3):
            raise ValueError
        for name in ("operation_id", "previous_history", "history", "base_profile"):
            if (
                not isinstance(item[name], str)
                or not item[name]
                or len(cast(str, item[name])) > 16384
            ):
                raise ValueError
        if item["format"] == 3:
            previous = item.get("previous_manifest")
            if type(previous) is not str or len(previous) > 32768:
                raise ValueError
            if previous and _manifest(previous, store)["format"] != 2:
                raise ValueError
        if item["base_profile"] != store.base_profile:
            raise ConfigurationError("Storage activation belongs to another configuration")
        return item
    except (TypeError, ValueError, KeyError) as error:
        raise ConfigurationError("Storage format manifest is invalid or unsupported") from error


async def _adopt(store: RedisStore, raw: object) -> dict[str, object]:
    manifest = _manifest(raw, store)
    profile = _profile(store, cast(int, manifest["format"]))
    history = cast(str, manifest["history"])
    valid = await store.connection.script(
        _VALIDATE,
        [*store.base_keys, f"{store.prefix}:live", _key(store)],
        [profile, history, text(raw)],
        mutation=False,
    )
    if valid != 1:
        raise PersistenceUnavailable("Storage activation witness is inconsistent")
    store.storage_format, store.profile, store.history = (
        cast(int, manifest["format"]),
        profile,
        history,
    )
    return manifest


BOOTSTRAP3 = """
local existing=redis.call('GET',KEYS[4])
if existing then return {'existing',existing} end
local profile=redis.call('GET',KEYS[1]); local witness=redis.call('GET',KEYS[2])
if profile or witness or redis.call('EXISTS',KEYS[3])~=0 then
 if profile and witness and redis.call('SISMEMBER',KEYS[3],'!established')==1 then return {'legacy'} end
 return {'history'}
end
local t=redis.call('TIME'); local history=t[1]..':'..t[2]..':'..ARGV[2]
local manifest=cjson.encode({format=3,operation_id='bootstrap:'..ARGV[2],previous_history=history,history=history,base_profile=ARGV[3],previous_manifest=''})
redis.call('SET',KEYS[1],ARGV[1]); redis.call('SET',KEYS[2],history)
redis.call('SADD',KEYS[3],'!established'); redis.call('SET',KEYS[4],manifest)
return {'ok',manifest}
"""


async def initialize_format(store: RedisStore) -> None:
    raw = await store.connection.call("GET", _key(store))
    requested = store.requested_storage_format
    if raw is not None:
        manifest = _manifest(raw, store)
        if requested is not None and manifest["format"] != requested:
            raise ConfigurationError(
                "Existing storage format differs; explicit drained migration is required"
            )
        await _adopt(store, raw)
    elif requested == 3:
        result = array(
            await store.connection.script(
                BOOTSTRAP3,
                [*store.base_keys, f"{store.prefix}:live", _key(store)],
                [_profile(store, 3), secrets.token_urlsafe(18), store.base_profile],
            )
        )
        if text(result[0]) == "legacy":
            raise ConfigurationError("Existing legacy storage requires explicit drained migration")
        if text(result[0]) not in ("ok", "existing"):
            raise PersistenceUnavailable(
                "Fresh storage bootstrap found inconsistent namespace history"
            )
        manifest = await _adopt(store, result[1])
        if manifest["format"] != 3:
            raise ConfigurationError("Existing storage requires explicit drained migration")


async def _inventory(store: RedisStore) -> tuple[int, int]:
    cursor = "0"
    members: set[str] = set()
    for _ in range(max(100, store.config.max_conversations * 2)):
        response = array(
            await store.connection.script(
                SCAN_PAGE,
                [*store.base_keys, f"{store.prefix}:live"],
                [store.profile, store.history, cursor, 100],
                mutation=False,
            )
        )
        if text(response[0]) != "ok":
            raise PersistenceUnavailable("Storage history changed during activation assessment")
        cursor = str(response[1]) if type(response[1]) is int else text(response[1])
        if not cursor.isdecimal():
            raise PersistenceUnavailable("Activation scan cursor is malformed")
        members.update(text(item) for item in array(response[2]) if text(item) != "!established")
        if len(members) > store.config.max_conversations:
            raise PersistenceUnavailable("Storage index exceeds its configured capacity")
        if cursor == "0":
            break
    else:
        raise PersistenceUnavailable("Storage activation assessment exceeded its bounded scan")
    pending = 0
    from ..models import ConversationKey

    for member in members:
        key = decode(member)
        if not isinstance(key, ConversationKey):
            raise PersistenceUnavailable("Activation index contains an invalid identity")
        response = array(
            await store.connection.script(
                READ, store.keys(key), [store.profile, store.history, member], mutation=False
            )
        )
        if text(response[0]) != "ok":
            raise PersistenceUnavailable("Storage history changed during read-only assessment")
        raw = text(response[1])
        if raw:
            header = json.loads(raw)
            if header.get("schema_version") == 3 and header.get("kind") == "hot":
                pending += int(header.get("pending_id") is not None)
            else:
                pending += int(loads(raw, key, engine=store.config.engine).pending_id is not None)
    return len(members), pending


async def activate_storage_format(
    store: RedisStore,
    *,
    expected: int = 1,
    target: int = 2,
    operation_id: str,
    old_workers_drained: bool = False,
    dry_run: bool = True,
) -> StorageMigrationReport:
    if (
        type(expected) is not int
        or type(target) is not int
        or (expected, target) not in ((1, 2), (1, 3), (2, 3))
    ):
        raise ConfigurationError(
            "Only drained format 1/2 upgrades to a newer supported format are allowed"
        )
    if (
        not isinstance(cast(object, operation_id), str)
        or not operation_id
        or len(operation_id) > 256
        or type(old_workers_drained) is not bool
        or type(dry_run) is not bool
    ):
        raise ConfigurationError("Invalid storage activation arguments")
    try:
        identifier(operation_id, "operation_id")
    except ValueError as error:
        raise ConfigurationError(str(error)) from error
    if not dry_run and (not old_workers_drained or store.coordinator.active_scopes):
        raise ConfigurationError("Drain all old writers and local scopes before activation")
    if dry_run and not store.initialized:
        profile = await store.connection.call("GET", store.base_keys[0])
        history = await store.connection.call("GET", store.base_keys[1])
        indexed = await store.connection.call("EXISTS", f"{store.prefix}:live")
        manifest = await store.connection.call("GET", _key(store))
        if profile is None and history is None and indexed == 0 and manifest is None:
            return StorageMigrationReport(1, target, False, 0, 0)
    await store.initialize()
    raw = await store.connection.call("GET", _key(store))
    previous = text(raw) if raw is not None else ""
    manifest = await _adopt(store, raw) if raw is not None else None
    duplicate = (
        manifest is not None
        and manifest["operation_id"] == operation_id
        and manifest["format"] == target
    )
    if (
        manifest is not None
        and manifest["operation_id"] == operation_id
        and manifest["format"] != target
    ):
        raise OperationIdConflict("Activation operation ID has different intent")
    before = store.storage_format
    if not dry_run and manifest is not None and manifest["format"] == target and not duplicate:
        raise OperationIdConflict("Storage activation was committed by another operation")
    if not dry_run and not duplicate and before != expected:
        raise ConfigurationError("Storage format changed; review before retrying")
    records, pending = await _inventory(store)
    if dry_run or duplicate:
        return StorageMigrationReport(before, target, not dry_run, records, pending)
    history = f"{store.history}:format{target}:{secrets.token_urlsafe(18)}"
    values = dict(
        format=target,
        operation_id=operation_id,
        previous_history=store.history,
        history=history,
        base_profile=store.base_profile,
    )
    if target == 3:
        values["previous_manifest"] = previous
    manifest_raw = json.dumps(values, sort_keys=True, separators=(",", ":"))
    result = array(
        await store.connection.script(
            ACTIVATE,
            [*store.base_keys, f"{store.prefix}:live", _key(store)],
            [
                store.profile,
                store.history,
                _profile(store, target),
                history,
                manifest_raw,
                previous,
            ],
        )
    )
    if text(result[0]) not in {"ok", "existing"}:
        raise PersistenceUnavailable("Storage history changed before activation commit")
    persisted = _manifest(result[1], store)
    if persisted["operation_id"] != operation_id or persisted["format"] != target:
        raise OperationIdConflict("Storage activation was committed by another operation")
    await _adopt(store, result[1])
    return StorageMigrationReport(before, target, True, records, pending)


async def migrate_page(
    store: RedisStore, *, cursor: str = "0:0", limit: int = 100
) -> dict[str, object]:
    """Convert a bounded idempotent page after explicit format-three activation.

    The cursor contains only scan offsets, never conversation identities. Concurrent
    admissions have SSCAN's usual weak-snapshot semantics; another assessment/pass
    can complete any newly admitted conversations without redoing effects.
    """
    if (
        type(limit) is not int
        or not 1 <= limit <= 1000
        or type(cursor) is not str
        or len(cursor) > 64
    ):
        raise ConfigurationError("Migration page requires a bounded limit and scan cursor")
    parts = cursor.split(":")
    if len(parts) != 2 or any(not value.isdecimal() for value in parts):
        raise ConfigurationError("Migration cursor is malformed")
    scan, offset = parts[0], int(parts[1])
    if offset > store.config.max_conversations:
        raise ConfigurationError("Migration cursor exceeds the configured namespace capacity")
    if not store.initialized and store.requested_storage_format != 3:
        manifest_raw = await store.connection.call("GET", _key(store))
        if manifest_raw is None or _manifest(manifest_raw, store)["format"] != 3:
            raise ConfigurationError("Activate storage format 3 before migrating records")
    await store.initialize()
    if store.storage_format != 3:
        raise ConfigurationError("Activate storage format 3 before migrating records")
    response = array(
        await store.connection.script(
            SCAN_PAGE,
            [*store.base_keys, f"{store.prefix}:live"],
            [store.profile, store.history, scan, limit],
            mutation=False,
        )
    )
    if text(response[0]) != "ok":
        raise PersistenceUnavailable("Storage history changed during migration")
    next_scan = str(response[1]) if type(response[1]) is int else text(response[1])
    members = [text(value) for value in array(response[2]) if text(value) != "!established"]
    selected = members[offset : offset + limit]
    converted = 0
    from ..models import ConversationKey

    for member in selected:
        key = decode(member)
        if not isinstance(key, ConversationKey):
            raise PersistenceUnavailable("Migration index contains an invalid identity")
        snapshot = array(
            await store.connection.script(
                READ, store.keys(key), [store.profile, store.history, member], mutation=False
            )
        )
        if text(snapshot[0]) != "ok":
            raise PersistenceUnavailable("Storage history changed before record conversion")
        raw = text(snapshot[1])
        if raw and json.loads(raw).get("schema_version") in (1, 2):
            await store.read(key)
            converted += 1
    if offset + len(selected) < len(members):
        remaining = f"{scan}:{offset + len(selected)}"
    else:
        remaining = f"{next_scan}:0" if next_scan != "0" else None
    return dict(cursor=remaining, inspected=len(selected), converted=converted)
