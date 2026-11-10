"""Explicit namespace-format activation; records migrate only on normal CAS writes."""

from __future__ import annotations

# Namespace bookkeeping deliberately uses the store's internal transaction API.
# pyright: reportPrivateUsage=false
import json
import secrets
from typing import TYPE_CHECKING, cast

from ..codec import decode, encode
from ..errors import ConfigurationError, OperationIdConflict, PersistenceUnavailable
from .redis_codec import loads
from .redis_scripts import SCAN_PAGE
from .redis_transport import array, text
from .sessions import StorageMigrationReport

if TYPE_CHECKING:
    from .redis_store import RedisStore

ACTIVATE = """
local existing = redis.call('GET', KEYS[4])
if existing then return {'existing', existing} end
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


def _profile(store: RedisStore) -> str:
    return encode({"storage_format": 2, "base_profile": decode(store.base_profile)})


def _manifest(raw: object, store: RedisStore) -> dict[str, object]:
    try:
        value: object = json.loads(text(raw))
        if not isinstance(value, dict):
            raise ValueError
        item = cast(dict[str, object], value)
        if set(item) != {"format", "operation_id", "previous_history", "history", "base_profile"}:
            raise ValueError
        if type(item["format"]) is not int or item["format"] != 2:
            raise ValueError
        for name in ("operation_id", "previous_history", "history", "base_profile"):
            if (
                not isinstance(item[name], str)
                or not item[name]
                or len(cast(str, item[name])) > 16384
            ):
                raise ValueError
        if item["base_profile"] != store.base_profile:
            raise ConfigurationError("Storage activation belongs to another configuration")
        return item
    except (TypeError, ValueError, KeyError) as error:
        raise ConfigurationError("Storage format manifest is invalid or unsupported") from error


async def _adopt(store: RedisStore, raw: object) -> dict[str, object]:
    manifest = _manifest(raw, store)
    profile = _profile(store)
    history = cast(str, manifest["history"])
    valid = await store.connection.script(
        _VALIDATE,
        [*store.base_keys, f"{store.prefix}:live", _key(store)],
        [profile, history, text(raw)],
        mutation=False,
    )
    if valid != 1:
        raise PersistenceUnavailable("Storage activation witness is inconsistent")
    store.storage_format, store.profile, store.history = 2, profile, history
    return manifest


async def initialize_format(store: RedisStore) -> None:
    raw = await store.connection.call("GET", _key(store))
    if raw is not None:
        await _adopt(store, raw)


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
        raw, _ = await store.read(key)
        pending += int(bool(raw and loads(raw, key).pending_id is not None))
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
    if type(expected) is not int or expected != 1 or type(target) is not int or target != 2:
        raise ConfigurationError("Only the explicit format 1 to 2 upgrade is supported")
    if (
        not isinstance(cast(object, operation_id), str)
        or not operation_id
        or len(operation_id) > 256
        or type(old_workers_drained) is not bool
        or type(dry_run) is not bool
    ):
        raise ConfigurationError("Invalid storage activation arguments")
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
    duplicate = False
    if raw is not None:
        manifest = _manifest(raw, store)
        if not dry_run and manifest["operation_id"] != operation_id:
            raise OperationIdConflict("Storage activation was committed by another operation")
        await _adopt(store, raw)
        duplicate = True
    elif store.storage_format != expected:
        raise ConfigurationError("Storage format changed; review before retrying")
    records, pending = await _inventory(store)
    before = store.storage_format
    if dry_run or duplicate:
        return StorageMigrationReport(before, target, not dry_run, records, pending)
    history = f"{store.history}:format2:{secrets.token_urlsafe(18)}"
    manifest_raw = json.dumps(
        {
            "format": 2,
            "operation_id": operation_id,
            "previous_history": store.history,
            "history": history,
            "base_profile": store.base_profile,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    result = array(
        await store.connection.script(
            ACTIVATE,
            [*store.base_keys, f"{store.prefix}:live", _key(store)],
            [store.profile, store.history, _profile(store), history, manifest_raw],
        )
    )
    if text(result[0]) not in {"ok", "existing"}:
        raise PersistenceUnavailable("Storage history changed before activation commit")
    persisted = _manifest(result[1], store)
    if persisted["operation_id"] != operation_id:
        raise OperationIdConflict("Storage activation was committed by another operation")
    await _adopt(store, result[1])
    return StorageMigrationReport(before, target, True, records, pending)
