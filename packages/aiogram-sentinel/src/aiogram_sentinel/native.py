"""Explicit optional native selection; failure never falls back after mutation."""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast

from .exceptions import ConfigurationError
from .version import __version__


class NativeEngineUnavailable(ConfigurationError):
    """The explicitly requested optional extension cannot be imported."""


class NativeEngineIncompatible(ConfigurationError):
    """The extension does not implement this package's exact version and ABI."""


class RateCore(Protocol):
    def allow(self, key: bytes, maximum: int, window: float, now: float) -> bool: ...
    def remaining(self, key: bytes, maximum: int, window: float, now: float) -> int: ...
    def increment(self, key: bytes, window: float, now: float) -> int: ...
    def count(self, key: bytes, now: float) -> int: ...
    def reset(self, key: bytes) -> None: ...
    def snapshot(self) -> list[tuple[list[int], list[float]]]: ...


class DebounceCore(Protocol):
    def seen(
        self, key: bytes, window: float, fingerprint: bytes, now: float
    ) -> bool: ...
    def set(self, key: bytes, delay: float, now: float) -> None: ...
    def active(self, key: bytes, now: float) -> bool: ...
    def snapshot(self) -> list[tuple[list[int], float]]: ...


class NativeModule(Protocol):
    def capabilities(self) -> tuple[str, int, str]: ...
    def RateLimiterCore(self) -> RateCore: ...
    def DebounceCore(self) -> DebounceCore: ...


def load_native() -> NativeModule:
    try:
        module = import_module("_aiogram_sentinel_native")
    except (ImportError, OSError) as error:
        raise NativeEngineUnavailable(
            f"Rust engine requires aiogram-sentinel-native=={__version__}; "
            "install a compatible platform wheel or select engine='python'"
        ) from error
    try:
        native = cast(NativeModule, module)
        capabilities: object = native.capabilities()
        if (
            type(capabilities) is not tuple
            or len(capabilities) != 3
            or type(capabilities[0]) is not str
            or type(capabilities[1]) is not int
            or type(capabilities[2]) is not str
            or capabilities != ("aiogram-sentinel-native", 1, __version__)
        ):
            raise ValueError("Native capability/version mismatch")
        if not callable(native.RateLimiterCore) or not callable(native.DebounceCore):
            raise ValueError("Missing native kernel")
        # Validate the whole ABI before exposing either backend. Construction is
        # pure: never probe methods by calling operations that could mutate state.
        for core, methods in (
            (
                native.RateLimiterCore(),
                ("allow", "remaining", "increment", "count", "reset", "snapshot"),
            ),
            (native.DebounceCore(), ("seen", "set", "active", "snapshot")),
        ):
            if any(not callable(getattr(core, method, None)) for method in methods):
                raise ValueError("Incomplete native kernel interface")
    except Exception as error:
        raise NativeEngineIncompatible(
            "Rust engine requires matching aiogram-sentinel-native version and ABI1"
        ) from error
    return native


def validate_engine(engine: object) -> None:
    if engine not in ("python", "rust"):
        raise ConfigurationError("engine must be python or rust")
