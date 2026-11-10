"""Explicit immutable config/translation snapshots and resolved batch payloads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import cast

from aiogram.types import BotCommand

from .builder import validate_name
from .builders_configured import build_from_config
from .customize import CmdsConfig
from .delivery import UNSET, LanguageCode, menu_slot
from .engines import Engine, NativeRows, NativeSnapshot, Rows, native_engine
from .registry import CommandRegistry
from .scopes import ScopeObject, scope_object, sorted_scopes
from .translator import Translator


def _revision(value: str, name: str) -> None:
    if not isinstance(cast(object, value), str) or not value or len(value) > 256:
        raise ValueError(f"{name} must contain 1..256 characters")


@dataclass(frozen=True)
class ProfileRequest:
    profile: str
    language: str
    bot_id: int
    scope_json: str
    language_code: str | None | LanguageCode = UNSET


@dataclass(frozen=True)
class ResolvedPayload:
    """Immutable strings only; materialize fresh SDK models at the API boundary."""

    commands: Rows
    fingerprint: str
    scope_json: str
    language_code: str | None

    def bot_commands(self) -> list[BotCommand]:
        return [
            BotCommand(command=name, description=description)
            for name, description in self.commands
        ]


@dataclass(frozen=True)
class CompiledCommands:
    config_revision: str
    translation_revision: str | None
    config_json: str
    profiles: Mapping[str, Mapping[str, Rows]]
    encoded: Mapping[str, Mapping[str, str]] = field(init=False, repr=False)
    scopes: tuple[tuple[str, str, tuple[str, ...], bool], ...]
    menu_button: str
    per_language: bool
    native: NativeSnapshot | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _revision(self.config_revision, "config_revision")
        if self.translation_revision is not None:
            _revision(self.translation_revision, "translation_revision")
        frozen: dict[str, Mapping[str, Rows]] = {}
        encoded: dict[str, Mapping[str, str]] = {}
        for profile, locales in self.profiles.items():
            captured: dict[str, Rows] = {}
            serialized: dict[str, str] = {}
            for locale, rows in locales.items():
                fresh = tuple(
                    (command.command, command.description)
                    for command in (
                        BotCommand(command=n, description=d) for n, d in rows
                    )
                )
                if any(
                    validate_name(n) != n or not d or len(d) > 256 for n, d in fresh
                ):
                    raise ValueError("Invalid resolved compiled commands")
                captured[locale] = fresh
                serialized[locale] = json.dumps(
                    [{"command": n, "description": d} for n, d in fresh],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            frozen[profile] = MappingProxyType(captured)
            encoded[profile] = MappingProxyType(serialized)
        object.__setattr__(self, "profiles", MappingProxyType(frozen))
        object.__setattr__(self, "encoded", MappingProxyType(encoded))
        object.__setattr__(
            self,
            "scopes",
            tuple(
                (scope, profile, tuple(locales), per)
                for scope, profile, locales, per in self.scopes
            ),
        )

    def bind(self, engine: Engine = "python") -> CompiledCommands:
        module = native_engine(engine)
        if module is None or self.native is not None:
            return self
        from dataclasses import replace

        bound = replace(self)
        object.__setattr__(bound, "native", module.compile(self.native_rows()))
        return bound

    def native_rows(self) -> NativeRows:
        return [
            (profile, [(locale, list(rows)) for locale, rows in locales.items()])
            for profile, locales in self.profiles.items()
        ]

    def rows(self, profile: str, language: str) -> Rows:
        try:
            return self.profiles[profile][language]
        except KeyError as error:
            raise ValueError(
                "Unknown compiled profile/locale; compile a new explicit revision"
            ) from error

    def config(self) -> CmdsConfig:
        """Return an independent mutable copy, never the snapshot's configuration."""
        return CmdsConfig.model_validate_json(self.config_json)

    def targets(self) -> tuple[tuple[ScopeObject, str | None, list[BotCommand]], ...]:
        # SDK scope objects are fresh just like command objects.
        from .customize import ScopeDef

        result: list[tuple[ScopeObject, str | None, list[BotCommand]]] = []
        for scope_json, profile, locales, per_language in self.scopes:
            scope = scope_object(ScopeDef.model_validate_json(scope_json))
            for language in locales if per_language else locales[:1]:
                result.append(
                    (
                        scope,
                        language if per_language else None,
                        [
                            BotCommand(command=n, description=d)
                            for n, d in self.rows(profile, language)
                        ],
                    )
                )
        return tuple(result)


def compile_config(
    config: CmdsConfig,
    *,
    config_revision: str,
    translator: Translator | None = None,
    translation_revision: str | None = None,
    locales: Sequence[str] | None = None,
    engine: Engine = "python",
) -> CompiledCommands:
    """Capture translator results now; caller must rebuild for every new revision.

    No manager implicitly compiles/caches a mutable config or dynamic translator.
    A compiled snapshot intentionally continues to represent its original inputs.
    """
    module = native_engine(engine)
    _revision(config_revision, "config_revision")
    if translator is not None and translation_revision is None:
        raise ValueError("Explicit translation_revision is required with a translator")
    if translation_revision is not None:
        _revision(translation_revision, "translation_revision")
    copied = config.model_copy(deep=True)
    wanted = (
        list(locales)
        if locales is not None
        else list(
            dict.fromkeys(
                [
                    *(copied.languages or ["en"]),
                    *(lang for scope in copied.scopes for lang in scope.languages),
                ]
            )
        )
    )
    if not wanted or any(
        not isinstance(cast(object, locale), str) or not locale for locale in wanted
    ):
        raise ValueError("Compiled locales must contain nonempty strings")
    reg = CommandRegistry(copied)
    profiles: dict[str, Mapping[str, Rows]] = {}
    for profile, definition in copied.profiles.items():
        names = (
            module.resolve_profile(
                definition.include, definition.exclude, list(copied.commands)
            )
            if module
            else reg.resolve_profile_commands(profile)
        )
        per_locale: dict[str, Rows] = {}
        for language in dict.fromkeys(wanted):
            commands = build_from_config(
                reg,
                names,
                lang=language,
                translator=translator,
                key_prefix=copied.i18n_key_prefix,
            )
            per_locale[language] = tuple(
                (command.command, command.description) for command in commands
            )
        profiles[profile] = MappingProxyType(per_locale)
    scopes = tuple(
        (
            scope.model_dump_json(),
            scope.profile,
            tuple(scope.languages or copied.languages or ["en"]),
            copied.per_language if scope.per_language is None else scope.per_language,
        )
        for scope in sorted_scopes(copied.scopes)
    )
    # Validate scopes/declared locales before publishing a usable snapshot.
    for scope in copied.scopes:
        scope_object(scope)
        for language in scope.languages or copied.languages or ["en"]:
            if scope.profile not in profiles or language not in profiles[scope.profile]:
                raise ValueError(
                    "A configured target is absent from the compiled profiles/locales"
                )
    snapshot = CompiledCommands(
        config_revision,
        translation_revision,
        copied.model_dump_json(),
        MappingProxyType(profiles),
        scopes,
        copied.menu_button.mode,
        copied.per_language,
    )
    return snapshot.bind(engine)


def build_profile_batch(
    compiled: CompiledCommands,
    requests: Sequence[ProfileRequest],
    *,
    engine: Engine = "python",
) -> tuple[ResolvedPayload, ...]:
    """Resolve all payloads and hashes before any Telegram/network effect."""
    module = native_engine(engine)
    prepared: list[tuple[ProfileRequest, Rows, dict[str, object], str, str | None]] = []
    for request in requests:
        if type(request.bot_id) is not int or request.bot_id <= 0:
            raise ValueError("A positive bot identity is required for fingerprints")
        scope = json.loads(request.scope_json)
        if not isinstance(scope, dict):
            raise ValueError("scope_json must describe an SDK scope object")
        scope = cast(dict[str, object], scope)
        canonical = json.dumps(
            scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        slot = menu_slot(
            request.language, request.language_code, per_language=compiled.per_language
        )
        prepared.append(
            (
                request,
                compiled.rows(request.profile, request.language),
                scope,
                canonical,
                slot,
            )
        )
    if module is None:
        results: list[ResolvedPayload] = []
        for request, rows, _scope, canonical, slot in prepared:
            language = json.dumps(slot, ensure_ascii=False)
            commands = compiled.encoded[request.profile][request.language]
            value = f'{{"bot_id":{request.bot_id},"commands":{commands},"language_code":{language},"scope":{canonical}}}'
            digest = hashlib.sha256(value.encode()).hexdigest()
            results.append(ResolvedPayload(rows, digest, canonical, slot))
        return tuple(results)
    native = compiled.native or module.compile(compiled.native_rows())
    hashes = native.resolve_batch(
        [
            (
                request.profile,
                request.language,
                str(request.bot_id),
                canonical,
                json.dumps(slot, ensure_ascii=False),
            )
            for request, _, _, canonical, slot in prepared
        ]
    )
    return tuple(
        ResolvedPayload(rows, digest, canonical, slot)
        for (_, rows, _, canonical, slot), digest in zip(prepared, hashes, strict=True)
    )
