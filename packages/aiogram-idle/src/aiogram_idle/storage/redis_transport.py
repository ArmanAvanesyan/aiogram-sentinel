"""Redis transport and server-authoritative clock; never falls back to local state."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
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
        self.sample_count = 0
        self.last_jump_seconds: float | None = None

    def update(self, seconds: float) -> None:
        now = time.monotonic()
        jump = seconds - (self._server + now - self._mono) if self._server is not None else None
        if jump is not None and abs(jump) > 1:
            self.last_jump_seconds = jump
            logging.getLogger(__name__).warning(
                "Redis clock jumped; deadline and lease timing may have changed"
            )
        self.sample_count += 1
        self._server = seconds
        self._mono = now

    def diagnostics(self) -> dict[str, int | float | None]:
        """Clock observations only; an interpolated read is not a fresh server sample."""
        return {
            "sample_count": self.sample_count,
            "sample_age_seconds": max(0.0, time.monotonic() - self._mono)
            if self._server is not None
            else None,
            "last_jump_seconds": self.last_jump_seconds,
        }

    def now(self) -> float:
        if self._server is None:
            raise PersistenceUnavailable("Redis backend must be initialized before use")
        return self._server + time.monotonic() - self._mono

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

    async def time(self) -> float:
        parts = array(await self.call("TIME"))
        value = (
            int(str(parts[0]) if isinstance(parts[0], int) else text(parts[0]))
            + int(str(parts[1]) if isinstance(parts[1], int) else text(parts[1])) / 1_000_000
        )
        self.clock.update(value)
        return value

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
                if error.__class__.__name__ == "NoScriptError" or "NOSCRIPT" in str(error):
                    if attempt == 1:
                        raise PersistenceUnavailable(
                            "Redis script cache remained unavailable"
                        ) from error
                    await self.call("SCRIPT", "LOAD", source)
                    continue
                if _is_response_error(error):
                    if "IDLE_INCONSISTENT namespace history" in str(error):
                        raise BackendInconsistent(
                            "Redis namespace history was lost or replaced; explicit recovery required"
                        ) from error
                    raise BackendInconsistent(
                        "Redis script failed; effects must stop pending reconciliation"
                    ) from error
                kind = CommitUnknown if mutation else PersistenceUnavailable
                raise kind("Redis script result is uncertain") from error
        raise AssertionError("Unreachable script retry state")
