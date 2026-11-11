"""Explicit deterministic engines. Python retains I/O, clocks, random IDs and locks."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
from functools import lru_cache
from typing import TYPE_CHECKING, Literal, Protocol, cast

from .errors import ActivityConflict, ConfigurationError

if TYPE_CHECKING:
    from ._native_queue import NativeDeadlineCore
    from .storage.queue import DeadlineQueue

EngineName = Literal["python", "rust"]
ActivityTuple = tuple[str, str, int, float]
SessionTuple = tuple[str, int, float]


class NativeCore(Protocol):
    API_VERSION: int
    ENGINE_VERSION: str
    OwnershipLost: type[Exception]

    def DeadlineCore(self) -> NativeDeadlineCore: ...
    def phase_transition(self, phase: str, trigger: str) -> str: ...
    def fingerprint_canonical(self, raw: str) -> str: ...
    def receipt_admission(
        self, existing: str | None, digest: str, retained_count: str, limit: str
    ) -> str: ...
    def activity_guard(
        self, actual: tuple[str, str, str, float] | None, expected: tuple[str, str, str], now: float
    ) -> str | None: ...
    def session_guard(
        self, actual: tuple[str, str, float] | None, expected: tuple[str, str] | None, now: float
    ) -> str | None: ...
    def claim_guard(
        self, actual: tuple[str, str, float] | None, expected: tuple[str, str], now: float
    ) -> str | None: ...


@lru_cache(maxsize=1)
def native_core() -> NativeCore:
    """Validate the complete exact-version ABI before any engine-owned mutation."""
    try:
        module = cast(
            NativeCore, importlib.import_module("aiogram_idle_native._aiogram_idle_native")
        )
    except (ImportError, OSError) as error:
        raise ConfigurationError("engine='rust' requires aiogram-idle-native==0.3.1") from error
    required = (
        "DeadlineCore",
        "phase_transition",
        "fingerprint_canonical",
        "receipt_admission",
        "activity_guard",
        "session_guard",
        "claim_guard",
        "OwnershipLost",
    )
    if (
        type(getattr(module, "API_VERSION", None)) is not int
        or getattr(module, "API_VERSION", None) != 1
        or type(getattr(module, "ENGINE_VERSION", None)) is not str
        or getattr(module, "ENGINE_VERSION", None) != "0.3.1"
        or any(not callable(getattr(module, name, None)) for name in required)
    ):
        raise ConfigurationError("Incompatible aiogram-idle-native engine ABI/version")
    try:
        probe = module.DeadlineCore()
        queue_methods = (
            "get",
            "put",
            "remove",
            "clear",
            "push",
            "schedule",
            "check",
            "claim",
            "renew",
            "release",
            "reconcile",
            "keys",
            "heap",
            "heap_len",
        )
        ownership_error = cast(object, module.OwnershipLost)
        compatible = (
            isinstance(ownership_error, type)
            and issubclass(ownership_error, Exception)
            and probe.sequence == "0"
            and all(callable(getattr(probe, name, None)) for name in queue_methods)
        )
    except Exception as error:
        raise ConfigurationError("Incompatible aiogram-idle-native engine ABI/version") from error
    if not compatible:
        raise ConfigurationError("Incompatible aiogram-idle-native engine ABI/version")
    return module


def require_engine(engine: str) -> None:
    if engine not in ("python", "rust"):
        raise ConfigurationError("engine must be 'python' or 'rust'")
    if engine == "rust":
        native_core()


_TRANSITIONS = {
    ("active", "due_prompt"): "prompt_pending",
    ("active", "due_restore"): "restoring",
    ("prompt_pending", "shown"): "prompted",
    ("prompt_pending", "unknown_delivery"): "delivery_unknown",
    ("prompted", "continue"): "resuming",
    ("delivery_unknown", "continue"): "resuming",
    ("prompted", "cancel"): "abandoning",
    ("delivery_unknown", "cancel"): "abandoning",
    ("prompted", "timeout"): "abandoning",
    ("resuming", "finish"): "active",
    ("abandoning", "finish"): "disarmed",
    ("restoring", "finish"): "disarmed",
}
_PHASES = frozenset(
    {
        "disarmed",
        "active",
        "prompt_pending",
        "prompted",
        "delivery_unknown",
        "resuming",
        "abandoning",
        "restoring",
        "effect_unknown",
        "quarantined",
    }
)


def phase_transition(phase: str, trigger: str, *, engine: EngineName = "python") -> str:
    if engine == "rust":
        try:
            return native_core().phase_transition(phase, trigger)
        except ValueError as error:
            raise ActivityConflict("invalid idle transition") from error
    if phase not in _PHASES:
        raise ActivityConflict("invalid idle transition")
    if trigger in {"clear", "exhausted", "unknown_effect"}:
        return {
            "clear": "disarmed",
            "exhausted": "quarantined",
            "unknown_effect": "effect_unknown",
        }[trigger]
    if trigger in {"enter", "touch"} and phase in {
        "disarmed",
        "active",
        "prompted",
        "delivery_unknown",
    }:
        return "active"
    try:
        return _TRANSITIONS[phase, trigger]
    except KeyError as error:
        raise ActivityConflict("invalid idle transition") from error


def fingerprint_canonical(raw: str, *, engine: EngineName = "python") -> str:
    return (
        native_core().fingerprint_canonical(raw)
        if engine == "rust"
        else hashlib.sha256(raw.encode()).hexdigest()
    )


def receipt_admission(
    existing: str | None,
    digest: str,
    retained_count: int,
    limit: int,
    *,
    engine: EngineName = "python",
) -> str:
    if engine == "rust":
        return native_core().receipt_admission(
            existing, digest, format(retained_count, "x"), format(limit, "x")
        )
    if existing is not None:
        return "duplicate" if existing == digest else "conflict"
    return "capacity" if retained_count >= limit else "admit"


def _finite(*values: float) -> None:
    if not all(math.isfinite(value) for value in values):
        raise ValueError("clock and expiry values must be finite")


def activity_guard(
    actual: ActivityTuple | None,
    expected: tuple[str, str, int],
    now: float,
    *,
    engine: EngineName = "python",
) -> str | None:
    if engine == "rust":
        return native_core().activity_guard(
            (_wire(actual[0]), _wire(actual[1]), format(actual[2], "x"), actual[3])
            if actual
            else None,
            (_wire(expected[0]), _wire(expected[1]), format(expected[2], "x")),
            now,
        )
    _finite(now, *(actual[3:] if actual else ()))
    if actual is None or actual[:3] != expected:
        return "conflict"
    return "expired" if actual[3] <= now else None


def session_guard(
    actual: SessionTuple | None,
    expected: tuple[str, int] | None,
    now: float,
    *,
    engine: EngineName = "python",
) -> str | None:
    if engine == "rust":
        return native_core().session_guard(
            (_wire(actual[0]), format(actual[1], "x"), actual[2]) if actual else None,
            (_wire(expected[0]), format(expected[1], "x")) if expected else None,
            now,
        )
    _finite(now, *(actual[2:] if actual else ()))
    if actual is None or actual[2] <= now:
        return "expired"
    return "conflict" if expected is not None and actual[:2] != expected else None


def claim_guard(
    actual: tuple[str, int, float] | None,
    expected: tuple[str, int],
    now: float,
    *,
    engine: EngineName = "python",
) -> str | None:
    if engine == "rust":
        return native_core().claim_guard(
            (_wire(actual[0]), format(actual[1], "x"), actual[2]) if actual else None,
            (_wire(expected[0]), format(expected[1], "x")),
            now,
        )
    _finite(now, *(actual[2:] if actual else ()))
    return (
        None if actual is not None and actual[:2] == expected and actual[2] > now else "ownership"
    )


def _wire(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def make_queue(engine: EngineName = "python") -> DeadlineQueue:
    require_engine(engine)
    if engine == "rust":
        from ._native_queue import RustDeadlineQueue

        return RustDeadlineQueue()
    from .storage.queue import DeadlineQueue

    return DeadlineQueue()
