"""Explicit deterministic engine selection; I/O and ownership stay in Python."""

from __future__ import annotations

import importlib
import json
from functools import lru_cache
from typing import Literal, Protocol, cast

from .errors import ConfigurationError

EngineName = Literal["python", "rust"]


class NativeRegistry(Protocol):
    def ancestors(self, id: str) -> list[str]: ...
    def root_for(self, id: str) -> str: ...
    def back_target(self, id: str) -> str | None: ...
    def cancel_target(self, id: str) -> str: ...
    def resolve(self, id: str) -> str: ...


class NativeCore(Protocol):
    API_VERSION: int
    ENGINE_VERSION: str

    def Registry(self, raw: str) -> NativeRegistry: ...

    def strict_loads(self, raw: str, max_bytes: int, max_depth: int) -> object: ...
    def fingerprint_canonical(self, raw: str) -> str: ...
    def transition_history(
        self,
        history_json: str,
        current_entry_json: str | None,
        mode: str,
        limit: int,
        pop: int,
        push_current: bool,
    ) -> str: ...
    def transition_state(
        self,
        old_json: str | None,
        node_id: str,
        params_changed: bool,
        accepted_activity: bool,
        now_ms: str,
    ) -> str: ...
    def token_matches(
        self,
        token_key: str,
        current_key: str,
        token_actor: str,
        actor: str,
        token_session: str,
        current_session: str,
        token_view: str,
        current_view: str,
        expires_at: str,
        now_ms: str,
    ) -> bool: ...


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


@lru_cache(maxsize=1)
def native_core() -> NativeCore:
    try:
        module = cast(NativeCore, importlib.import_module("aiogram_nav_native._aiogram_nav_native"))
    except ImportError as error:
        raise ConfigurationError("engine='rust' requires aiogram-nav-native>=0.3.0,<0.4") from error
    abi = getattr(module, "API_VERSION", None)
    functions = (
        "Registry",
        "strict_loads",
        "fingerprint_canonical",
        "transition_state",
        "transition_history",
        "token_matches",
    )
    if (
        type(abi) is not int
        or abi != 1
        or getattr(module, "ENGINE_VERSION", None) != "0.3.0"
        or not all(callable(getattr(module, name, None)) for name in functions)
    ):
        raise ConfigurationError("Incompatible aiogram-nav-native engine ABI/version")
    return module


def require_engine(engine: EngineName) -> None:
    if engine not in ("python", "rust"):
        raise ConfigurationError("engine must be 'python' or 'rust'")
    if engine == "rust":
        native_core()


def strict_loads(raw: str, *, engine: EngineName, max_bytes: int) -> object:
    if engine == "rust":
        # Typed codec validation independently enforces logical depth <=64.
        return native_core().strict_loads(raw, max_bytes, 512)
    return json.loads(raw, object_pairs_hook=_pairs)
