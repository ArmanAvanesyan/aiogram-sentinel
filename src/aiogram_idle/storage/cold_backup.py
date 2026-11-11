"""Explicit inspection/export/cleanup of one bounded immutable legacy source backup."""

from __future__ import annotations

# Administrative operations reuse backend-owned observation/coordination internals.
# pyright: reportPrivateUsage=false
import base64
import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..errors import BackendInconsistent, ConfigurationMismatch, OwnershipLost, VersionConflict
from ..models import IdleConversationKey
from .codec import decode
from .cold import MAX_EXACT_MILLISECONDS, ColdState
from .cold_migration import (
    MAX_SOURCE_BYTES,
    _absolute_expiry,
    _protected,
    backup_keys,
    migration_key,
    source_summary,
)
from .redis_engine import Engine
from .redis_scripts import _TYPES
from .redis_transport import array, text
from .wire_json import strict

if TYPE_CHECKING:
    from .redis_store import RedisStore

_READ = (
    _TYPES
    + r"""
if not types(KEYS,{'string','string','string','string','string'}) then return redis.error_reply('IDLE_INCONSISTENT migration backup type') end
if not namespace(KEYS[3],ARGV[1],KEYS[4],KEYS[5]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
return {redis.call('GET',KEYS[1]) or '',redis.call('GET',KEYS[2]) or '',redis.call('PEXPIRETIME',KEYS[1]),redis.call('PEXPIRETIME',KEYS[2])}
"""
)
_CLEAN = (
    _TYPES
    + r"""
local expected={'string','string','string','string','string','string','string','hash'}
for i=9,#KEYS do expected[i]='hash' end
if not types(KEYS,expected) then return redis.error_reply('IDLE_INCONSISTENT migration cleanup type') end
if not namespace(KEYS[4],ARGV[1],KEYS[5],KEYS[6]) then return redis.error_reply('IDLE_INCONSISTENT namespace history') end
if redis.call('GET',KEYS[7])~=ARGV[5] or redis.call('PTTL',KEYS[7])<=0 then return 'ownership' end
if (redis.call('GET',KEYS[1]) or '')~=ARGV[2] or (redis.call('GET',KEYS[2]) or '')~=ARGV[3]
 or (redis.call('GET',KEYS[3]) or '')~=ARGV[4] or (redis.call('GET',KEYS[5]) or '')~=ARGV[6] then return 'conflict' end
local staged=redis.call('HGET',KEYS[8],'source')
if staged and (staged~=ARGV[7] or redis.call('HLEN',KEYS[8])~=4 or redis.call('HGET',KEYS[8],'key')~=ARGV[8]) then return 'conflict' end
if not staged and redis.call('HLEN',KEYS[8])>0 then return 'conflict' end
for i=9,#KEYS do if redis.call('EXISTS',KEYS[i])~=0 then return 'canonical_pending' end end
redis.call('DEL',KEYS[1],KEYS[2],KEYS[8]); return 'ok'
"""
)


@dataclass(frozen=True)
class BackupInspection:
    key: IdleConversationKey
    backup_key: str
    source_digest: str
    bytes: int
    protected: bool
    expires_at: int | None
    original_replay_until: int


@dataclass(frozen=True)
class BackupPage:
    cursor: str
    items: tuple[BackupInspection, ...]
    count: int
    bytes: int


async def _read(
    store: RedisStore, key: IdleConversationKey
) -> tuple[BackupInspection, str, str] | None:
    await store.initialize()
    backup, metadata = backup_keys(store, key)
    values = array(
        await store.connection.script(
            _READ,
            [
                backup,
                metadata,
                store.prefix + ":created",
                store.prefix + ":config",
                store.prefix + ":config-established",
            ],
            [store.history],
            mutation=False,
        )
    )
    if len(values) != 4:
        raise BackendInconsistent("Invalid migration backup response")
    raw, encoded = text(values[0]), text(values[1])
    if not raw and not encoded:
        return None
    if not raw or not encoded:
        raise BackendInconsistent("Immutable migration backup or proof is missing")
    proof = strict(encoded)
    if (
        set(proof)
        != {
            "schema_version",
            "kind",
            "history",
            "key",
            "source_sha256",
            "bytes",
            "protected",
            "original_replay_until",
            "expires_at",
        }
        or proof["schema_version"] != 3
        or proof["kind"] != "idle-migration-source"
        or proof["history"] != store.history
        or proof["key"] != store.member(key)
        or type(proof["bytes"]) is not int
        or not 0 < proof["bytes"] <= MAX_SOURCE_BYTES
        or len(raw.encode()) != proof["bytes"]
        or type(proof["protected"]) is not bool
        or proof["source_sha256"] != hashlib.sha256(raw.encode()).hexdigest()
    ):
        raise BackendInconsistent("Immutable migration source identity changed")
    source_record, _, original_until = source_summary(raw)
    if (
        source_record.key != key
        or proof["protected"] != _protected(source_record)
        or proof["original_replay_until"] != original_until
    ):
        raise BackendInconsistent("Migration backup lifetime contradicts its source")
    protected = proof["protected"]
    expiry = proof["expires_at"]
    if protected:
        if expiry is not None or values[2] != -1 or values[3] != -1:
            raise BackendInconsistent("Protected migration backup has an expiry")
    elif (
        type(expiry) is not int
        or not 0 < expiry <= MAX_EXACT_MILLISECONDS
        or values[2] != expiry
        or values[3] != expiry
    ):
        raise BackendInconsistent("Migration backup expiry changed")
    return (
        BackupInspection(
            key,
            backup,
            cast(str, proof["source_sha256"]),
            proof["bytes"],
            protected,
            expiry,
            original_until,
        ),
        raw,
        encoded,
    )


async def inspect_backup(store: RedisStore, key: IdleConversationKey) -> BackupInspection | None:
    """Verify source hash/full identity without returning application payloads."""
    value = await _read(store, key)
    return value[0] if value else None


async def export_backup(
    store: RedisStore, key: IdleConversationKey, *, expected_digest: str
) -> str:
    """Explicit administrator export; no automatic replay or restoring old hot state."""
    value = await _read(store, key)
    if value is None or value[0].source_digest != expected_digest:
        raise VersionConflict("Migration backup changed before export")
    return value[1]


async def cleanup_backup(
    store: RedisStore,
    key: IdleConversationKey,
    *,
    expected_digest: str,
    canonical_rows_verified: bool = False,
    unresolved_evidence_preserved: bool = False,
) -> bool:
    """Explicit proof-attested cleanup, never an automatic protected-backup GC.

    The administrator attests that every still-promised canonical row is verified
    and unresolved business/adapter evidence is independently preserved or resolved.
    The library additionally verifies hash, full identity, current hot state and a
    shared-lock CAS. It never replaces hot state with historical source content.
    """
    if canonical_rows_verified is not True or unresolved_evidence_preserved is not True:
        raise ConfigurationMismatch(
            "Verify canonical rows and unresolved evidence before backup cleanup"
        )
    await store.initialize()
    if store.migration_scope is None:
        raise ConfigurationMismatch("Backup cleanup requires the verified conversation coordinator")
    async with store.migration_scope(key):
        value = await _read(store, key)
        if value is None:
            return False
        inspection, raw, proof = value
        if inspection.source_digest != expected_digest:
            raise VersionConflict("Migration backup changed before cleanup")
        engine, hot, config = await store.read(key)
        context = engine.cold_state
        if not isinstance(context, ColdState) or context.legacy:
            raise ConfigurationMismatch("Complete forward migration before backup cleanup")
        source = Engine(
            key=key,
            raw=raw,
            job="",
            manifest=store.config_value(config),
            now=store.clock.now(),
            config=store.config,
            created_at=store.created_at,
            storage_format=3,
        )
        original = source._receipts.items.get(key, {})
        promised = [
            name
            for name, receipt in original.items()
            if _absolute_expiry(receipt) > store.clock.now() * 1000
        ]
        # Inspect a bounded page for concrete contradictions. No attestation may
        # authorize early removal: earlier page checks cannot prove every row still
        # exists at final cutover under external deletion. Wait the original window.
        for name in sorted(promised)[:32]:
            observed, _, _ = await store.read(key, operation_id=name)
            replay = observed._receipts.items.get(key, {}).get(name)
            previous = original[name]
            if (
                replay is None
                or replay.fingerprint != previous.fingerprint
                or replay.result != previous.result
                or round(replay.expires_at * 1000) != _absolute_expiry(previous)
            ):
                raise BackendInconsistent("Promised canonical replay contradicts migration source")
        if promised:
            raise ConfigurationMismatch(
                "Original replay windows must expire before conservative backup cleanup"
            )
        previous_record = source._records.get(key)
        current_record = engine._records.get(key)
        if (
            inspection.protected
            and previous_record is not None
            and previous_record.idle.operation is not None
            and current_record is None
        ):
            raise ConfigurationMismatch(
                "Protected source requires an inspectable forward recovery state"
            )
        if (
            previous_record is not None
            and previous_record.idle.operation is not None
            and current_record is not None
            and current_record.idle.operation is None
            and current_record.idle.phase.value in {"effect_unknown", "quarantined"}
        ):
            raise BackendInconsistent("Forward state lost unresolved operation evidence")
        if (
            previous_record is not None
            and previous_record.idle.operation is not None
            and current_record is not None
            and current_record.idle.operation is not None
        ):
            old, new = previous_record.idle.operation, current_record.idle.operation
            if (
                old.operation_id != new.operation_id
                or old.kind != new.kind
                or old.started_at != new.started_at
            ):
                raise BackendInconsistent(
                    "Forward recovery contradicts the original pending identity"
                )
            if old.action_receipt is not None and old.action_receipt != new.action_receipt:
                raise BackendInconsistent("Forward recovery lost its original accepted result")
            for stage, evidence in old.effects.items():
                latest = new.effects.get(stage)
                if stage not in new.effects or (evidence == "confirmed" and latest != "confirmed"):
                    raise BackendInconsistent("Forward recovery lost protected effect evidence")
                if evidence != latest and (
                    not isinstance(evidence, str)
                    or not isinstance(latest, str)
                    or evidence not in {"started", "confirmed", "not_sent", "unknown"}
                    or latest not in {"started", "confirmed", "not_sent", "unknown"}
                ):
                    raise BackendInconsistent("Forward recovery changed opaque effect evidence")
        fence = store.fencer(key)
        if fence is None:
            raise OwnershipLost("Backup cleanup ownership ended")
        backup, metadata = backup_keys(store, key)
        from .canonical_redis import component_prefix

        components = (
            previous_record.components if previous_record is not None else dict[str, object]()
        )
        if len(components) > 1000:
            raise ConfigurationMismatch("Backup cleanup component-inspection budget exceeded")
        component_progress = [
            component_prefix(store, key, name) + ":migration" for name in components
        ]
        result = text(
            await store.connection.script(
                _CLEAN,
                [
                    backup,
                    metadata,
                    store.keys(key)[0],
                    store.prefix + ":created",
                    store.prefix + ":config",
                    store.prefix + ":config-established",
                    fence[0],
                    migration_key(store, key),
                    *component_progress,
                ],
                [
                    store.history,
                    raw,
                    proof,
                    hot,
                    fence[1],
                    config,
                    expected_digest,
                    store.member(key),
                ],
            )
        )
        if result == "ownership":
            raise OwnershipLost("Backup cleanup ownership ended")
        if result == "canonical_pending":
            raise ConfigurationMismatch(
                "Complete canonical component copy and verification before backup cleanup"
            )
        if result != "ok":
            raise VersionConflict("Migration backup, current state or configuration changed")
        return True


async def list_backups(store: RedisStore, *, cursor: str = "0", limit: int = 32) -> BackupPage:
    """Bounded physical-backup inspection; page counts/bytes are not a cached total."""
    if (
        type(limit) is not int
        or not 1 <= limit <= 1000
        or type(cursor) is not str
        or len(cursor) > 8_388_608
    ):
        raise ValueError("Invalid bounded backup inspection cursor/limit")
    await store.initialize()
    pending: list[str] = []
    position = cursor
    if cursor.startswith("page:"):
        try:
            body = strict(base64.urlsafe_b64decode(cursor[5:].encode()).decode())
            if set(body) != {"cursor", "pending"}:
                raise ValueError
            raw_position, raw_pending = body["cursor"], body["pending"]
            if type(raw_position) is not str or not isinstance(raw_pending, list):
                raise ValueError
            if any(type(item) is not str for item in cast(list[object], raw_pending)):
                raise ValueError
            position, pending = raw_position, cast(list[str], raw_pending)
        except (ValueError, KeyError, UnicodeDecodeError) as error:
            raise ValueError("Malformed backup inspection cursor") from error
    if not position.isdecimal():
        raise ValueError("Malformed backup inspection cursor")
    prefix = store.prefix + ":cold-migration-proof:"
    if not pending:
        escaped = "".join("\\" + char if char in "\\*?[]" else char for char in prefix)
        page = array(
            await store.connection.call("SCAN", position, "MATCH", escaped + "*", "COUNT", limit)
        )
        position = str(page[0]) if isinstance(page[0], int) else text(page[0])
        pending = [text(item) for item in array(page[1])]
    selected, pending = pending[:limit], pending[limit:]
    items: list[BackupInspection] = []
    for name in selected:
        if not name.startswith(prefix):
            raise ValueError("Backup inspection cursor belongs to another namespace")
        payload = await store.connection.call("GET", name)
        if payload is None:
            continue
        header = strict(text(payload))
        key = decode(cast(str, header.get("key")))
        if not isinstance(key, IdleConversationKey) or backup_keys(store, key)[1] != name:
            raise BackendInconsistent("Backup inspection conversation identity changed")
        value = await inspect_backup(store, key)
        if value is not None:
            items.append(value)
    if pending:
        position = (
            "page:"
            + base64.urlsafe_b64encode(
                json.dumps({"cursor": position, "pending": pending}).encode()
            ).decode()
        )
    return BackupPage(position, tuple(items), len(items), sum(item.bytes for item in items))
