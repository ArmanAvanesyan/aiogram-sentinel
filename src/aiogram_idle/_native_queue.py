"""Typed native queue adapter; Rust owns every scheduling and lease decision."""

from __future__ import annotations

import json
import secrets
import weakref
from collections.abc import Callable, Iterator, MutableMapping, Sequence
from functools import lru_cache
from typing import Protocol, TypeVar, cast, overload

from .errors import OwnershipLost
from .models import IdleConversationKey, RuntimeSnapshot
from .storage.queue import DeadlineQueue
from .storage.state import Claim, Job

T = TypeVar("T")
JobTuple = tuple[str, float, float, str | None, float]
ClaimTuple = tuple[str, str, str, float, float]


class NativeDeadlineCore(Protocol):
    sequence: str

    def __len__(self) -> int: ...
    def heap_len(self) -> int: ...
    def heap(self) -> list[tuple[float, str, str]]: ...
    def keys(self) -> list[str]: ...
    def get(self, key: str) -> JobTuple | None: ...
    def remove(self, key: str) -> JobTuple | None: ...
    def clear(self) -> None: ...
    def put(
        self,
        key: str,
        namespace: str,
        bot_id: str,
        generation: str,
        deadline: float,
        eligible_at: float,
        token: str | None,
        lease_until: float,
    ) -> None: ...
    def push(self, key: str) -> None: ...
    def schedule(
        self,
        key: str,
        namespace: str,
        bot_id: str,
        deadline: float | None,
        preserve_token: str | None = None,
    ) -> None: ...
    def check(self, key: str, token: str, generation: str, now: float) -> JobTuple: ...
    def claim(
        self,
        limit: int,
        lease_seconds: float,
        now: float,
        tokens: list[str],
        namespace: str | None,
        bot_id: str | None,
    ) -> list[ClaimTuple]: ...
    def renew(
        self, key: str, token: str, generation: str, now: float, lease_seconds: float
    ) -> ClaimTuple: ...
    def release(
        self, key: str, token: str, generation: str, now: float, deadline: float | None
    ) -> None: ...
    def reconcile(self, candidates: list[tuple[str, str, str, float]], limit: int) -> int: ...


def _wire(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _unwire(value: str) -> str:
    return cast(str, json.loads(value))


@lru_cache(maxsize=16384)
def _key(key: IdleConversationKey) -> str:
    return json.dumps(
        (
            key.namespace,
            format(key.bot_id, "x"),
            format(key.chat_id, "x"),
            format(key.user_id, "x"),
            key.tenant_id,
        ),
        separators=(",", ":"),
    )


def _job(value: JobTuple) -> Job:
    return Job(
        int(value[0], 16),
        value[1],
        value[2],
        _unwire(value[3]) if value[3] is not None else None,
        value[4],
    )


def _unkey(value: str) -> IdleConversationKey:
    fields = cast(list[object], json.loads(value))
    return IdleConversationKey(
        cast(str, fields[0]),
        int(cast(str, fields[1]), 16),
        int(cast(str, fields[2]), 16),
        int(cast(str, fields[3]), 16),
        cast(str | None, fields[4]),
    )


class _Jobs(MutableMapping[IdleConversationKey, Job]):
    def __init__(self, queue: RustDeadlineQueue) -> None:
        self.queue = cast(RustDeadlineQueue, weakref.proxy(queue))

    def __getitem__(self, key: IdleConversationKey) -> Job:
        value = self.queue.core.get(_key(key))
        if value is None:
            raise KeyError(key)
        return _job(value)

    def __setitem__(self, key: IdleConversationKey, value: Job) -> None:
        packed = _key(key)
        self.queue.core.put(
            packed,
            _wire(key.namespace),
            format(key.bot_id, "x"),
            format(value.generation, "x"),
            value.deadline,
            value.eligible_at,
            _wire(value.token) if value.token is not None else None,
            value.lease_until,
        )
        self.queue.keys[packed] = key

    def __delitem__(self, key: IdleConversationKey) -> None:
        packed = _key(key)
        if self.queue.core.remove(packed) is None:
            raise KeyError(key)
        self.queue.keys.pop(packed, None)

    def __iter__(self) -> Iterator[IdleConversationKey]:
        return iter(tuple(self.queue.keys[value] for value in self.queue.core.keys()))

    def __len__(self) -> int:
        return len(self.queue.core)

    def clear(self) -> None:
        self.queue.core.clear()
        self.queue.keys.clear()


class _Heap(Sequence[tuple[float, int, IdleConversationKey]]):
    def __init__(self, queue: RustDeadlineQueue) -> None:
        self.queue = cast(RustDeadlineQueue, weakref.proxy(queue))

    def __len__(self) -> int:
        return self.queue.core.heap_len()

    @overload
    def __getitem__(self, index: int) -> tuple[float, int, IdleConversationKey]: ...
    @overload
    def __getitem__(self, index: slice) -> Sequence[tuple[float, int, IdleConversationKey]]: ...
    def __getitem__(
        self, index: int | slice
    ) -> tuple[float, int, IdleConversationKey] | Sequence[tuple[float, int, IdleConversationKey]]:
        values = [
            (at, int(sequence, 16), self.queue.keys.get(key) or _unkey(key))
            for at, sequence, key in self.queue.core.heap()
        ]
        return values[index]


class RustDeadlineQueue(DeadlineQueue):
    """Thin typed adapter; Rust owns all job, generation, heap and lease decisions."""

    # The public/private attributes keep the baseline backend's inspection shape.
    def __init__(self) -> None:
        from .engines import native_core

        self.native = native_core()
        self.core = self.native.DeadlineCore()
        self.keys: dict[str, IdleConversationKey] = {}
        self.jobs = cast(dict[IdleConversationKey, Job], _Jobs(self))
        self.heap = cast(list[tuple[float, int, IdleConversationKey]], _Heap(self))

    @property  # pyright: ignore[reportIncompatibleVariableOverride]
    def sequence(self) -> int:
        return int(self.core.sequence, 16)

    @sequence.setter
    def sequence(self, value: int) -> None:
        self.core.sequence = format(value, "x")

    def _owned(self, action: Callable[[], T]) -> T:
        try:
            return action()
        except self.native.OwnershipLost as error:
            raise OwnershipLost("The deadline claim has expired or was replaced") from error

    def _push(self, key: IdleConversationKey, job: Job) -> None:
        self.jobs[key] = job
        self.core.push(_key(key))

    def schedule(self, record: RuntimeSnapshot, *, preserve: Claim | None = None) -> None:
        from .storage.component_transaction import component_deadline

        key, packed = record.key, _key(record.key)
        self._owned(
            lambda: self.core.schedule(
                packed,
                _wire(key.namespace),
                format(key.bot_id, "x"),
                component_deadline(record),
                _wire(preserve.token) if preserve else None,
            )
        )
        if self.core.get(packed) is None:
            self.keys.pop(packed, None)
        else:
            self.keys[packed] = key

    def check(self, claim: Claim, now: float) -> Job:
        return _job(
            self._owned(
                lambda: self.core.check(
                    _key(claim.key), _wire(claim.token), format(claim.generation, "x"), now
                )
            )
        )

    def claim(
        self,
        *,
        limit: int,
        lease_seconds: float,
        now: float,
        namespace: str | None = None,
        bot_id: int | None = None,
    ) -> list[Claim]:
        bounded = min(limit, len(self.core))
        tokens = [_wire(secrets.token_urlsafe(18)) for _ in range(bounded)]
        rows = self._owned(
            lambda: self.core.claim(
                bounded,
                lease_seconds,
                now,
                tokens,
                _wire(namespace) if namespace is not None else None,
                format(bot_id, "x") if bot_id is not None else None,
            )
        )
        return [
            Claim(self.keys[key], _unwire(token), int(generation, 16), lease, deadline)
            for key, token, generation, lease, deadline in rows
        ]

    def renew(self, claim: Claim, *, now: float, lease_seconds: float) -> Claim:
        _, token, generation, lease, deadline = self._owned(
            lambda: self.core.renew(
                _key(claim.key),
                _wire(claim.token),
                format(claim.generation, "x"),
                now,
                lease_seconds,
            )
        )
        return Claim(claim.key, _unwire(token), int(generation, 16), lease, deadline)

    def release(
        self, claim: Claim, record: RuntimeSnapshot, *, now: float, retry_at: float | None = None
    ) -> None:
        from .storage.component_transaction import component_deadline

        deadline = retry_at if retry_at is not None else component_deadline(record)
        packed = _key(claim.key)
        self._owned(
            lambda: self.core.release(
                packed, _wire(claim.token), format(claim.generation, "x"), now, deadline
            )
        )
        if self.core.get(packed) is None:
            self.keys.pop(packed, None)

    def reconcile(self, records: Sequence[RuntimeSnapshot], *, limit: int) -> int:
        from .storage.component_transaction import component_deadline

        candidates: list[tuple[str, str, str, float]] = []
        selected: dict[str, IdleConversationKey] = {}
        for record in records[:limit]:
            deadline = component_deadline(record)
            if deadline is not None:
                packed = _key(record.key)
                candidates.append(
                    (packed, _wire(record.key.namespace), format(record.key.bot_id, "x"), deadline)
                )
                selected[packed] = record.key
        count = self.core.reconcile(candidates, min(limit, len(candidates)))
        self.keys.update(selected)
        return count
