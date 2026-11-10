"""Explicit Telegram menu slots and caller-owned confirmation fingerprints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Literal, cast

from aiogram.types import BotCommand

from .engines import Engine, native_engine


class LanguageCode(Enum):
    """UNSET keeps the historical language-specific menu behavior."""

    UNSET = "unset"


UNSET = LanguageCode.UNSET


def menu_slot(
    language: str,
    language_code: str | None | LanguageCode,
    *,
    per_language: bool = True,
) -> str | None:
    if not isinstance(cast(object, language), str) or not language:
        raise ValueError("Rendering language must be nonempty")
    if language_code is UNSET:
        return language if per_language else None
    if language_code is None or language_code == "":
        return None
    if not isinstance(cast(object, language_code), str):
        raise TypeError("language_code must be a string, None or UNSET")
    return language_code


def payload_fingerprint(
    bot_id: int,
    scope: dict[str, object],
    language_code: str | None,
    commands: list[BotCommand],
    *,
    engine: Engine = "python",
) -> str:
    if type(bot_id) is not int or bot_id <= 0:
        raise ValueError("A positive bot identity is required for fingerprints")
    module = native_engine(engine)
    if module is not None:
        return module.fingerprint(
            str(bot_id),
            json.dumps(
                scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            json.dumps(language_code, ensure_ascii=False),
            [(command.command, command.description) for command in commands],
        )
    payload = {
        "bot_id": bot_id,
        "scope": scope,
        "language_code": language_code,
        "commands": [
            {"command": command.command, "description": command.description}
            for command in commands
        ],
    }
    value = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class CommandApplyResult:
    """Only confirmed_fingerprint may be saved as a successful confirmation."""

    status: Literal["applied", "unchanged", "failed"]
    fingerprint: str | None = None
    confirmed_fingerprint: str | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class CommandBatchResult:
    """A batch is not atomic; successful targets remain applied after a failure."""

    status: Literal["applied", "partial", "failed"]
    completed_targets: tuple[str, ...] = ()
    failed_target: str | None = None
    error: Exception | None = None


def validate_fingerprint(previous_fingerprint: str | None) -> None:
    if previous_fingerprint is not None and (
        not isinstance(cast(object, previous_fingerprint), str)
        or len(previous_fingerprint) != 64
        or any(c not in "0123456789abcdef" for c in previous_fingerprint)
    ):
        raise ValueError("previous_fingerprint must be a confirmed SHA256 hex string")
