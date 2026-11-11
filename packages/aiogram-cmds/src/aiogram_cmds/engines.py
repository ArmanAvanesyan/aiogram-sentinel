"""Explicit optional native selection. Never import a compiler or silently fall back."""

from __future__ import annotations

from importlib import import_module
from typing import Literal, Protocol, cast

Engine = Literal["python", "rust"]
Rows = tuple[tuple[str, str], ...]
NativeRows = list[tuple[str, list[tuple[str, list[tuple[str, str]]]]]]
NativeRequests = list[tuple[str, str, str, str, str]]


class NativeEngineError(RuntimeError):
    """An explicitly requested native companion is missing or incompatible."""


class NativeSnapshot(Protocol):
    def resolve_batch(self, requests: NativeRequests) -> list[str]: ...


class NativeModule(Protocol):
    def abi_version(self) -> int: ...
    def version(self) -> str: ...
    def resolve_profile(
        self, include: list[str], exclude: list[str], known: list[str]
    ) -> list[str]: ...
    def validate_commands(self, rows: list[tuple[str, str]]) -> None: ...
    def fingerprint(
        self,
        bot_id: str,
        scope_json: str,
        language_json: str,
        rows: list[tuple[str, str]],
    ) -> str: ...
    def compile(self, rows: NativeRows) -> NativeSnapshot: ...


def native_engine(engine: Engine = "python") -> NativeModule | None:
    if engine not in ("python", "rust"):
        raise ValueError("engine must be 'python' or 'rust'")
    if engine == "python":
        return None
    try:
        module = cast(NativeModule, import_module("_aiogram_cmds_native"))
    except (ImportError, OSError) as error:
        raise NativeEngineError(
            "engine='rust' requires the separately installed aiogram-cmds-native companion"
        ) from error
    try:
        abi = module.abi_version()
        version = module.version()
        required = ("resolve_profile", "validate_commands", "fingerprint", "compile")
        if (
            type(abi) is not int
            or abi != 1
            or type(version) is not str
            or version != "0.3.1"
            or any(not callable(getattr(module, name, None)) for name in required)
        ):
            raise NativeEngineError(
                "aiogram-cmds-native ABI/version is incompatible with this base package"
            )
    except (AttributeError, TypeError, ValueError) as error:
        raise NativeEngineError(
            "aiogram-cmds-native does not expose the required ABI"
        ) from error
    return module
