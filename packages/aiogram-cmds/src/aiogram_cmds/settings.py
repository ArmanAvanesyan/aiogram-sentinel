"""
Standalone settings for aiogram_cmds package.

This module provides settings dataclass and configuration loading
from pyproject.toml, making the library configurable without hardcoded values.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from pydantic import BaseModel, ConfigDict, field_validator


class CmdsSettings(BaseModel):
    """Configuration settings for command management."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    languages: tuple[str, ...] = ("en",)
    fallback_language: str = "en"
    i18n_key_prefix: str = "cmd"
    profile: str = "default"
    menu_button: str = "commands"  # "commands" | "default"

    @field_validator("languages", mode="before")
    @classmethod
    def _ensure_nonempty(cls, v: object) -> tuple[object, ...]:
        if v is None:
            return ("en",)
        if isinstance(v, str):
            return (v,)
        if isinstance(v, (list, tuple)):
            return tuple(cast(Sequence[object], v)) if v else ("en",)
        return ("en",)


def load_settings(pyproject_path: Path | None = None) -> CmdsSettings:
    """
    Load settings from [tool.aiogram_cmds] in pyproject.toml (if present).
    """
    p = pyproject_path or Path("pyproject.toml")
    if not p.exists():
        return CmdsSettings()
    try:
        data = cast(dict[str, object], tomllib.loads(p.read_text(encoding="utf-8")))
        tool: object = data.get("tool") or dict[str, object]()
        if not isinstance(tool, Mapping):
            raise ValueError("Expected a TOML tool table")
        cfg: object = (
            cast(Mapping[str, object], tool).get("aiogram_cmds") or dict[str, object]()
        )
        return CmdsSettings.model_validate(cfg)
    except Exception as ex:  # pragma: no cover
        logging.getLogger(__name__).warning(
            "aiogram_cmds: failed to load settings: %s", ex
        )
        return CmdsSettings()
