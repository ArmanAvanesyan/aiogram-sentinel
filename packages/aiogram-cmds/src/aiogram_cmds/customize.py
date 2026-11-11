"""
Full customizable configuration models for aiogram_cmds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ScopeType = Literal[
    "default",
    "all_private_chats",
    "all_group_chats",
    "all_chat_admins",
    "chat",
    "chat_admins",
    "chat_member",
]


class CommandDef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # Either use i18n_key OR inline descriptions per language
    i18n_key: str | None = None
    descriptions: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ProfileDef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class ScopeDef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scope: ScopeType
    profile: str
    chat_id: int | None = None
    user_id: int | None = None
    languages: list[str] = Field(default_factory=list)  # empty = use global languages
    per_language: bool | None = None  # None inherits CmdsConfig.per_language


class MenuButtonDef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: Literal["commands", "default"] = "commands"


class CmdsConfig(BaseModel):
    """
    Full customizable configuration:
    - languages, fallback language, i18n key prefix
    - commands registry (with i18n_key or inline descriptions)
    - profiles: named sets of commands (include/exclude)
    - scopes: where to apply which profile
    - menu button config
    """

    model_config = ConfigDict(extra="ignore")
    languages: list[str] = ["en"]
    per_language: bool = True
    fallback_language: str = "en"
    i18n_key_prefix: str = "cmd"
    commands: dict[str, CommandDef] = Field(default_factory=dict)
    profiles: dict[str, ProfileDef] = Field(default_factory=dict)
    scopes: list[ScopeDef] = Field(default_factory=lambda: list[ScopeDef]())
    menu_button: MenuButtonDef = Field(default_factory=MenuButtonDef)
