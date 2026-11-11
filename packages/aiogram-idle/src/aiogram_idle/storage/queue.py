"""Generation-checked heap operations shared by the memory backend."""

from __future__ import annotations

import heapq
import secrets
from typing import TYPE_CHECKING

from ..errors import OwnershipLost
from .component_transaction import component_deadline
from .state import Claim, Job

if TYPE_CHECKING:
    from ..models import IdleConversationKey, RuntimeSnapshot


class DeadlineQueue:
    """Called only while its owning backend lock is held."""

    def __init__(self) -> None:
        self.jobs: dict[IdleConversationKey, Job] = {}
        self.heap: list[tuple[float, int, IdleConversationKey]] = []
        self.sequence = 0

    def _push(self, key: IdleConversationKey, job: Job) -> None:
        self.sequence += 1
        heapq.heappush(self.heap, (job.eligible_at, self.sequence, key))
        if len(self.heap) > 2 * len(self.jobs) + 128:
            self.heap = []
            for item_key, current in self.jobs.items():
                self.sequence += 1
                self.heap.append((current.eligible_at, self.sequence, item_key))
            heapq.heapify(self.heap)

    def schedule(self, record: RuntimeSnapshot, *, preserve: Claim | None = None) -> None:
        key = record.key
        deadline = component_deadline(record)
        current = self.jobs.get(key)
        if preserve is not None:
            if current is None or current.token != preserve.token:
                raise OwnershipLost("The deadline claim is no longer owned")
            if deadline is not None:
                current.deadline = deadline
            return
        generation = self.sequence + 1
        self.jobs.pop(key, None)
        if deadline is not None:
            job = Job(generation, deadline, deadline)
            self.jobs[key] = job
            self._push(key, job)

    def check(self, claim: Claim, now: float) -> Job:
        job = self.jobs.get(claim.key)
        if (
            job is None
            or job.generation != claim.generation
            or job.token != claim.token
            or job.lease_until <= now
        ):
            raise OwnershipLost("The deadline claim has expired or was replaced")
        return job

    def claim(
        self,
        *,
        limit: int,
        lease_seconds: float,
        now: float,
        namespace: str | None = None,
        bot_id: int | None = None,
    ) -> list[Claim]:
        claims: list[Claim] = []
        deferred: dict[IdleConversationKey, Job] = {}
        while self.heap and len(claims) < limit:
            eligible, _, key = self.heap[0]
            if eligible > now:
                break
            heapq.heappop(self.heap)
            job = self.jobs.get(key)
            if job is None or job.eligible_at != eligible:
                continue
            if job.token is not None and job.lease_until > now:
                continue
            if (namespace is not None and key.namespace != namespace) or (
                bot_id is not None and key.bot_id != bot_id
            ):
                deferred[key] = job
                continue
            job.token = secrets.token_urlsafe(18)
            job.lease_until = now + lease_seconds
            job.eligible_at = job.lease_until
            self._push(key, job)
            claims.append(Claim(key, job.token, job.generation, job.lease_until, job.deadline))
        for key, job in deferred.items():
            self._push(key, job)
        return claims

    def renew(self, claim: Claim, *, now: float, lease_seconds: float) -> Claim:
        job = self.check(claim, now)
        job.lease_until = now + lease_seconds
        job.eligible_at = job.lease_until
        self._push(claim.key, job)
        return Claim(claim.key, claim.token, claim.generation, job.lease_until, job.deadline)

    def release(
        self, claim: Claim, record: RuntimeSnapshot, *, now: float, retry_at: float | None = None
    ) -> None:
        self.check(claim, now)
        self.jobs.pop(claim.key)
        deadline = retry_at if retry_at is not None else component_deadline(record)
        if deadline is not None:
            job = Job(self.sequence + 1, deadline, deadline)
            self.jobs[claim.key] = job
            self._push(claim.key, job)
