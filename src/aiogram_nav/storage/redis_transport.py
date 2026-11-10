"""Redis transport and server-authoritative clock; never falls back to local state."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Protocol, cast

from ..errors import BackendInconsistent, CommitUnknown, PersistenceUnavailable, SchemaUnsupported


class RedisClient(Protocol):
    async def execute_command(self, *args: object) -> object: ...


def text(value: object) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SchemaUnsupported("Redis contains unsupported binary state") from error
    if isinstance(value, str):
        return value
    raise SchemaUnsupported("Redis returned an unexpected value type")


def _is_response_error(error: Exception) -> bool:
    # redis-py server error subclasses retain ResponseError in their MRO.
    return any(cls.__name__ == "ResponseError" for cls in type(error).__mro__)


def array(value: object) -> list[object]:
    if not isinstance(value, (list, tuple)):
        raise SchemaUnsupported("Redis returned an unexpected array")
    return list(cast("list[object]", value))


class RedisClock:
    """Interpolates Redis TIME using monotonic elapsed time between server reads."""

    def __init__(self) -> None:
        self._server: float | None = None
        self._mono = 0.0

    def update(self, milliseconds: int) -> None:
        seconds = milliseconds / 1000
        now = time.monotonic()
        if self._server is not None and abs(seconds - (self._server + now - self._mono)) > 1:
            logging.getLogger(__name__).warning(
                "Redis clock jumped; deadline and lease timing may have changed"
            )
        self._server = seconds
        self._mono = now

    def now(self) -> int:
        if self._server is None:
            raise PersistenceUnavailable("Redis backend must be initialized before use")
        return int((self._server + time.monotonic() - self._mono) * 1000)

    def now_ms(self) -> int:
        return self.now()

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class Connection:
    def __init__(self, redis: object, clock: RedisClock) -> None:
        self.client = cast(RedisClient, redis)
        self.clock = clock

    async def call(self, *args: object, mutation: bool = False) -> object:
        try:
            return await asyncio.wait_for(self.client.execute_command(*args), timeout=5.0)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if mutation and _is_response_error(error):
                raise BackendInconsistent(
                    "Redis mutation failed; inspect authoritative state"
                ) from error
            kind = CommitUnknown if mutation else PersistenceUnavailable
            raise kind("Redis operation failed; authoritative state is unavailable") from error

    async def time(self) -> int:
        parts = array(await self.call("TIME"))

        def integer(value: object) -> int:
            return value if type(value) is int else int(text(value))

        milliseconds = integer(parts[0]) * 1000 + integer(parts[1]) // 1000
        self.clock.update(milliseconds)
        return milliseconds

    async def script(
        self, source: str, keys: list[str], args: list[object], *, mutation: bool = True
    ) -> object:
        sha = hashlib.sha1(source.encode(), usedforsecurity=False).hexdigest()
        for attempt in range(2):
            try:
                return await asyncio.wait_for(
                    self.client.execute_command("EVALSHA", sha, len(keys), *keys, *args),
                    timeout=5.0,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if any(cls.__name__ == "NoScriptError" for cls in type(error).__mro__) or (
                    _is_response_error(error) and str(error).startswith("NOSCRIPT ")
                ):
                    if attempt == 1:
                        raise PersistenceUnavailable(
                            "Redis script cache remained unavailable"
                        ) from error
                    await self.call("SCRIPT", "LOAD", source)
                    continue
                if _is_response_error(error):
                    raise BackendInconsistent(
                        "Redis script failed; effects must stop pending reconciliation"
                    ) from error
                kind = CommitUnknown if mutation else PersistenceUnavailable
                raise kind("Redis script result is uncertain") from error
        raise AssertionError("Unreachable script retry state")


@asynccontextmanager
async def bounded(seconds: float) -> AsyncGenerator[None, None]:
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("Timeout scope requires an asyncio task")
    cancelling = cast(Callable[[], int] | None, getattr(task, "cancelling", None))
    uncancel = cast(Callable[[], int] | None, getattr(task, "uncancel", None))
    baseline = cancelling() if cancelling is not None else 0
    expired = False
    consumed = False
    marker = object()
    legacy_marker = False
    legacy_previous: object = None

    def expire() -> None:
        nonlocal expired, legacy_marker, legacy_previous
        expired = True
        if cancelling is None:
            legacy_previous = getattr(task, "_cancel_message", None)
        task.cancel(marker)
        if cancelling is None and hasattr(task, "_cancel_message"):
            # CPython 3.10 has no cancellation counter. Pin its message so even
            # an external cancel(None) racing this cancellation remains distinct.
            # Other Task implementations fall back to the delivered marker.
            try:
                setattr(task, "_cancel_message", marker)  # noqa: B010 -- guarded 3.10-only attribute
            except (AttributeError, TypeError):
                pass
            else:
                legacy_marker = True

    def consume() -> int:
        nonlocal consumed
        if uncancel is not None and not consumed:
            consumed = True
            return uncancel()
        return cancelling() if cancelling is not None else 0

    handle = asyncio.get_running_loop().call_later(seconds, expire)
    try:
        yield
    except asyncio.CancelledError as exc:
        if expired:
            remaining = consume()
            owned = (
                remaining <= baseline
                if cancelling is not None
                else exc.args == (marker,)
                and (not legacy_marker or getattr(task, "_cancel_message", None) is marker)
            )
            if owned:
                raise asyncio.TimeoutError from exc
        raise
    finally:
        handle.cancel()
        if expired:
            if legacy_marker and getattr(task, "_cancel_message", None) is marker:
                # Restore an outer timeout marker, never an external cancellation.
                setattr(task, "_cancel_message", legacy_previous)  # noqa: B010
            # A body that suppresses CancelledError still must relinquish exactly
            # this timeout's request; external cancellation requests are retained.
            consume()
