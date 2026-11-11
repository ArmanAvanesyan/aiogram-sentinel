"""One atomic, one-receipt application activity activation."""

from __future__ import annotations

from collections.abc import Mapping

# Composition uses the owning backend's audited public domain operations under
# its task-owned lock. No application callback or network runs inside the lock.
# pyright: reportPrivateUsage=false
from copy import copy
from typing import TYPE_CHECKING, cast

from aiogram_coordination import ExternalSession

from ..errors import OperationIdConflict, SessionExpired
from ..models import ActivityGuard, ActivitySnapshot, IdleConversationKey
from ..policies import IdlePolicy
from ..registration import ActivityRegistration
from .receipts import fingerprint
from .session_bindings import EXTERNAL_SESSION

if TYPE_CHECKING:
    from .memory import MemoryIdleBackend


class FusedActivities:
    async def fused_activate(
        self,
        key: IdleConversationKey,
        registration: ActivityRegistration,
        *,
        external: ExternalSession | None,
        policy: IdlePolicy,
        operation_id: str,
        expected: ActivityGuard | None = None,
        enabled: bool = False,
        expected_manifest: str | None = None,
    ) -> ActivitySnapshot:
        owner = cast("MemoryIdleBackend", self)
        await owner.require_storage_format(3)
        async with owner._lock:
            now = owner._now()
            digest = fingerprint(
                (
                    "activate",
                    registration,
                    policy,
                    (external.session_id, external.absolute_expires_at) if external else None,
                    expected,
                )
            )
            # Preserve the exact result of format-2 accepted calls after migration.
            prior = owner._receipts.items.get(key, {}).get(operation_id)
            if prior is not None and prior.expires_at > now and prior.fingerprint != digest:
                result = prior.result
                if isinstance(result, ActivitySnapshot):
                    legacy = fingerprint(
                        (
                            "enter",
                            registration.activity_key,
                            registration.policy_id,
                            policy,
                            registration.adapter_key,
                            registration.params,
                            result.session_id,
                            result.expires_at,
                            expected,
                        )
                    )
                    binding = owner._records.get(key)
                    source = binding.components.get(EXTERNAL_SESSION) if binding else None
                    authorized_source = external is None or (
                        isinstance(source, Mapping)
                        and source.get("session_id") == external.session_id
                        and source.get("absolute_expires_at") == external.absolute_expires_at
                    )
                    if prior.fingerprint == legacy and authorized_source:
                        return result
                raise OperationIdConflict("The operation ID was reused for different input")
            duplicate = owner._receipts.prepare(key, operation_id, digest, now=now)
            if duplicate is not None:
                return cast(ActivitySnapshot, duplicate)
            before = owner._records.get(key)
            before_policy = owner._policies.get(key)
            before_job = copy(owner._queue.jobs.get(key))
            try:
                with owner._receipts.transient():
                    if external is not None:
                        session = await owner.bind_external_session(
                            key,
                            session_id=external.session_id,
                            revision=external.revision,
                            absolute_expires_at=external.absolute_expires_at,
                            operation_id="activate-binding",
                        )
                    else:
                        if before is None or before.session.expires_at <= now:
                            raise SessionExpired("Open a library session before activating a flow")
                        session = before.session
                    result = await owner.enter(
                        key,
                        registration.activity_key,
                        policy_id=registration.policy_id,
                        policy=policy,
                        adapter_key=registration.adapter_key,
                        params=registration.params,
                        session_id=session.session_id,
                        expires_at=session.expires_at,
                        operation_id="activate-entry",
                        expected=expected,
                        enabled=enabled,
                        expected_manifest=expected_manifest,
                    )
            except BaseException:
                if before is None:
                    owner._records.pop(key, None)
                else:
                    owner._records[key] = before
                if before_policy is None:
                    owner._policies.pop(key, None)
                else:
                    owner._policies[key] = before_policy
                if before_job is None:
                    owner._queue.jobs.pop(key, None)
                else:
                    owner._queue.jobs[key] = before_job
                    owner._queue._push(key, before_job)
                raise
            return owner._receipts.save(key, operation_id, digest, result, now=now)
