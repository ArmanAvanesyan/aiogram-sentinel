"""Ephemeral domain reduction over an authoritative Redis envelope.

No state survives an operation. MemoryIdleBackend supplies the same audited domain
rules; Redis CAS supplies cross-process atomicity and all persisted ownership.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import math
from collections.abc import Hashable
from dataclasses import replace
from typing import cast

from ..clock import ManualClock
from ..config import IdleConfig
from ..errors import BackendInconsistent, SchemaUnsupported
from ..models import ConfigManifest, IdleConversationKey, IdleSnapshot, Phase, RuntimeSnapshot
from ..policies import ExemptPolicy, PromptPolicy, QuietRestorePolicy
from .codec import decode, encode
from .memory import MemoryIdleBackend
from .state import ControlToken, Job, OperationReceipt


def job_decode(raw: str) -> Job:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for name, item in items:
            if name in result:
                raise BackendInconsistent("Duplicate Redis job field")
            result[name] = item
        return result

    try:
        value: object = json.loads(raw, object_pairs_hook=pairs)
    except ValueError as error:
        raise BackendInconsistent("Malformed Redis job") from error
    if not isinstance(value, dict):
        raise BackendInconsistent("Invalid Redis job")
    data = cast("dict[str, object]", value)
    if set(data) - {
        "generation",
        "deadline",
        "eligible_at",
        "token",
        "lease_until",
        "renew_id",
        "renew_at",
    } or not {"generation", "deadline", "eligible_at", "token", "lease_until"} <= set(data):
        raise BackendInconsistent("Invalid Redis job shape")
    renewal_at = data.get("renew_at")
    if renewal_at is not None and (
        isinstance(renewal_at, bool)
        or not isinstance(renewal_at, (int, float))
        or not math.isfinite(renewal_at)
    ):
        raise BackendInconsistent("Invalid Redis renewal ordering timestamp")
    renewal = data.get("renew_id")
    if renewal is not None and (not isinstance(renewal, str) or not renewal):
        raise BackendInconsistent("Invalid Redis renewal receipt")
    token = data.get("token")
    if token is not None and (not isinstance(token, str) or not token):
        raise BackendInconsistent("Invalid Redis job token")
    generation, deadline = data.get("generation"), data.get("deadline")
    eligible, lease = data.get("eligible_at"), data.get("lease_until")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
        or not all(
            isinstance(item, (int, float)) and not isinstance(item, bool) and -1e300 < item < 1e300
            for item in (deadline, eligible, lease)
        )
    ):
        raise BackendInconsistent("Invalid Redis job fields")
    return Job(
        generation,
        float(cast(float, deadline)),
        float(cast(float, eligible)),
        token,
        float(cast(float, lease)),
    )


def job_encode(job: Job | None) -> str:
    if job is None:
        return ""
    return json.dumps(
        {
            "generation": job.generation,
            "deadline": job.deadline,
            "eligible_at": job.eligible_at,
            "token": job.token,
            "lease_until": job.lease_until,
        },
        allow_nan=False,
        separators=(",", ":"),
    )


class Engine(MemoryIdleBackend):
    """One-operation scratch reducer, never a cache or availability fallback."""

    def __init__(
        self,
        *,
        key: IdleConversationKey,
        raw: str,
        job: str,
        manifest: ConfigManifest | None,
        now: float,
        config: IdleConfig,
        created_at: float,
        disarm_epoch: str = "",
    ) -> None:
        super().__init__(clock=ManualClock(now), config=config)
        self.key = key
        self.original_job = job
        self.disarm_epoch = disarm_epoch
        self.armed_epoch = disarm_epoch
        self._created_at = created_at
        self._manifest = manifest
        self._receipts.pruned_before = created_at - config.recovery_retention_seconds
        if raw:
            decoded = decode(raw)
            if not isinstance(decoded, dict):
                raise SchemaUnsupported("Invalid Redis runtime envelope")
            data = cast("dict[str, object]", decoded)
            if set(data) != {
                "record",
                "policy",
                "receipts",
                "pruned_before",
                "tokens",
                "armed_epoch",
            }:
                raise BackendInconsistent("Invalid Redis envelope shape")
            epoch = data.get("armed_epoch")
            if not isinstance(epoch, str) or len(epoch) > 256:
                raise BackendInconsistent("Invalid Redis arming epoch")
            self.armed_epoch = epoch
            record = data.get("record")
            if not isinstance(record, RuntimeSnapshot) or record.key != key:
                raise SchemaUnsupported("Invalid Redis runtime identity")
            self._records[key] = record
            policy = data.get("policy")
            if policy is not None:
                if not isinstance(policy, (ExemptPolicy, PromptPolicy, QuietRestorePolicy)):
                    raise BackendInconsistent("Invalid frozen policy")
                self._policies[key] = policy
            elif record.activity is not None:
                raise BackendInconsistent("Activity has no frozen policy")
            receipts, tokens, pruned = data["receipts"], data["tokens"], data["pruned_before"]
            if not isinstance(receipts, dict) or not isinstance(tokens, dict):
                raise BackendInconsistent("Invalid Redis recovery evidence")
            if (
                not isinstance(pruned, (float, int))
                or isinstance(pruned, bool)
                or not math.isfinite(pruned)
            ):
                raise BackendInconsistent("Invalid Redis receipt history")
            for name, receipt in cast("dict[object, object]", receipts).items():
                if (
                    not isinstance(name, str)
                    or not name
                    or not isinstance(receipt, OperationReceipt)
                ):
                    raise BackendInconsistent("Invalid Redis receipt")
            for name, token in cast("dict[object, object]", tokens).items():
                if (
                    not isinstance(name, str)
                    or not isinstance(token, ControlToken)
                    or token.token != name
                    or token.key != key
                ):
                    raise BackendInconsistent("Invalid Redis control token")
            self._receipts.items[key] = cast("dict[str, OperationReceipt[object]]", receipts)
            self._receipts.pruned_before = float(pruned)
            self._tokens[key] = cast("dict[str, ControlToken]", tokens)
        if job:
            current = job_decode(job)
            self._queue.jobs[key] = current
            self._queue.sequence = current.generation
            self._queue._push(key, current)

    def envelope(self) -> str:
        record = self._records.get(self.key)
        if record is None:
            return ""
        return encode(
            {
                "record": record,
                "armed_epoch": self.armed_epoch,
                "policy": self._policies.get(self.key),
                "receipts": self._receipts.items.get(self.key, {}),
                "pruned_before": self._receipts.pruned_before,
                "tokens": self._tokens.get(self.key, {}),
            }
        )

    def job(self) -> str:
        encoded = job_encode(self._queue.jobs.get(self.key))
        if encoded and self.original_job:
            old = cast("dict[str, object]", json.loads(self.original_job))
            new = cast("dict[str, object]", json.loads(encoded))
            if (
                old.get("token") == new.get("token")
                and old.get("generation") == new.get("generation")
                and "renew_id" in old
            ):
                new["renew_id"] = old["renew_id"]
                if "renew_at" in old:
                    new["renew_at"] = old["renew_at"]
                return json.dumps(new, allow_nan=False, separators=(",", ":"))
        return encoded

    def manifest(self) -> ConfigManifest | None:
        return self._manifest

    def stale_active(self) -> bool:
        record = self._records.get(self.key)
        return (
            record is not None
            and record.idle.phase == Phase.ACTIVE
            and self.armed_epoch != self.disarm_epoch
        )

    def disarm_stale(self) -> None:
        if self.stale_active():
            self._save(replace(self._records[self.key], idle=IdleSnapshot()))

    def configuration_receipts(self) -> dict[Hashable, dict[str, OperationReceipt[object]]]:
        return self._config_receipts.items

    def restore_configuration_receipts(
        self, items: dict[Hashable, dict[str, OperationReceipt[object]]]
    ) -> None:
        self._config_receipts.items = items
