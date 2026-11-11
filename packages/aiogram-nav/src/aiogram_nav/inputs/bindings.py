"""Semantic entry declarations shared by commands, reply labels and callbacks."""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, cast

from aiogram import Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..errors import ConfigurationError, InvalidParameters
from ..json import JsonObject, empty_object, freeze_object, identifier
from ..models import NavigationAction

ActionKind = Literal["go", "back", "home", "cancel", "refresh"]
ArgumentDecoder = Callable[[CommandObject], Mapping[str, object] | Awaitable[Mapping[str, object]]]
Translator = Callable[[str, str], str]


def _validate_entry(entry_id: str, target: str | None, action: str, scope: frozenset[str]) -> None:
    identifier(entry_id, "entry ID")
    if action not in {"go", "back", "home", "cancel", "refresh"}:
        raise ConfigurationError("Unsupported navigation binding action")
    if action == "go" and not target:
        raise ConfigurationError("Go bindings require a destination")
    if action not in {"go", "home"} and target is not None:
        raise ConfigurationError("Only go/home bindings may declare a destination")
    if target is not None:
        identifier(target, "binding target")
    for node in scope:
        identifier(node, "source node")


@dataclass(frozen=True)
class CommandEntry:
    id: str
    command: str
    target: str | None = None
    from_nodes: frozenset[str] = frozenset()
    action: ActionKind = "go"
    global_action: bool = False
    decoder: ArgumentDecoder | None = None
    params: JsonObject = field(default_factory=empty_object)

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_nodes", frozenset(self.from_nodes))
        object.__setattr__(self, "params", freeze_object(self.params))
        _validate_entry(self.id, self.target, self.action, self.from_nodes)
        if not isinstance(cast(object, self.global_action), bool):
            raise ConfigurationError("Global navigation flags must be boolean")
        if self.decoder is not None and not callable(self.decoder):
            raise ConfigurationError("Command decoders must be callable")
        if not isinstance(cast(object, self.command), str) or not re.fullmatch(
            r"[A-Za-z0-9_]{1,32}", self.command
        ):
            raise ConfigurationError("Command bindings use a command name without a slash")


@dataclass(frozen=True)
class ReplyEntry:
    id: str
    text_key: str
    target: str | None = None
    from_nodes: frozenset[str] = frozenset()
    action: ActionKind = "go"
    global_action: bool = False
    params: JsonObject = field(default_factory=empty_object)

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_nodes", frozenset(self.from_nodes))
        object.__setattr__(self, "params", freeze_object(self.params))
        identifier(self.text_key, "translation key")
        if not isinstance(cast(object, self.global_action), bool):
            raise ConfigurationError("Global navigation flags must be boolean")
        _validate_entry(self.id, self.target, self.action, self.from_nodes)


@dataclass(frozen=True)
class CallbackEntry:
    id: str
    action: str
    target: str | None = None
    from_nodes: frozenset[str] = frozenset()
    kind: ActionKind = "go"
    params: JsonObject = field(default_factory=empty_object)

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_nodes", frozenset(self.from_nodes))
        object.__setattr__(self, "params", freeze_object(self.params))
        identifier(self.action, "callback action")
        _validate_entry(self.id, self.target, self.kind, self.from_nodes)


Entry = CommandEntry | ReplyEntry | CallbackEntry


@dataclass(frozen=True)
class MatchedEntry:
    entry: Entry
    params: JsonObject
    source: str

    @property
    def action(self) -> NavigationAction:
        kind = self.entry.kind if isinstance(self.entry, CallbackEntry) else self.entry.action
        return NavigationAction(kind=kind, target=self.entry.target, params=self.params)


def _allowed(entry: Entry, current_node: str | None) -> bool:
    return not entry.from_nodes or current_node in entry.from_nodes


def _overlap(first: Entry, second: Entry) -> bool:
    return (
        not first.from_nodes or not second.from_nodes or bool(first.from_nodes & second.from_nodes)
    )


class InputBindings:
    def __init__(self, entries: Iterable[Entry]) -> None:
        values = tuple(entries)
        if any(
            not isinstance(cast(object, entry), (CommandEntry, ReplyEntry, CallbackEntry))
            for entry in values
        ):
            raise ConfigurationError("Unsupported navigation entry declaration")
        if len({entry.id for entry in values}) != len(values):
            raise ConfigurationError("Navigation entry IDs must be unique")
        self._values = values
        self._entries = MappingProxyType({entry.id: entry for entry in values})
        for index, entry in enumerate(values):
            for other in values[index + 1 :]:
                if isinstance(entry, CommandEntry) and isinstance(other, CommandEntry):
                    if entry.command == other.command and _overlap(entry, other):
                        raise ConfigurationError("Command entries overlap within a source scope")
                if isinstance(entry, CallbackEntry) and isinstance(other, CallbackEntry):
                    if entry.action == other.action:
                        raise ConfigurationError("Callback action names must be unique")

    @property
    def entries(self) -> tuple[Entry, ...]:
        return self._values

    def validate(self, registry: object) -> None:
        from ..registry import NavigationRegistry

        if not isinstance(registry, NavigationRegistry):
            raise ConfigurationError("Bindings require a navigation registry")
        for entry in self.entries:
            kind = entry.kind if isinstance(entry, CallbackEntry) else entry.action
            for node_id in entry.from_nodes:
                registry.get(node_id)
            if entry.target is not None:
                node = registry.get(entry.target)
                if node.renderer is None:
                    raise ConfigurationError("Bindings cannot target abstract nodes")
                if kind == "home" and node.id not in registry.roots:
                    raise ConfigurationError("Home bindings must target a root")

    def entry(self, entry_id: str) -> Entry:
        try:
            return self._entries[entry_id]
        except KeyError as exc:
            raise ConfigurationError("Unknown navigation entry") from exc

    async def match_command(
        self,
        message: Message,
        bot: Bot,
        current_node: str | None,
        *,
        global_only: bool | None = None,
    ) -> MatchedEntry | None:
        for entry in self.entries:
            if not isinstance(entry, CommandEntry) or not _allowed(entry, current_node):
                continue
            if global_only is not None and entry.global_action != global_only:
                continue
            match = await Command(entry.command)(message, bot)
            if not match:
                continue
            if not isinstance(match, dict):
                raise ConfigurationError("aiogram did not supply a parsed command")
            command = cast(dict[str, object], match).get("command")
            if not isinstance(command, CommandObject):
                raise ConfigurationError("aiogram did not supply a parsed command")
            params = entry.params
            if entry.decoder is not None:
                try:
                    decoded = entry.decoder(command)
                    if inspect.isawaitable(decoded):
                        decoded = await decoded
                    params = freeze_object(decoded)
                except (ValueError, TypeError) as exc:
                    raise InvalidParameters("Command arguments were rejected") from exc
            elif command.args:
                raise InvalidParameters("This navigation command does not accept arguments")
            return MatchedEntry(entry, params, "command")
        return None

    def validate_labels(self, translator: Translator, *, locales: Iterable[str]) -> None:
        for locale in locales:
            entries = [entry for entry in self.entries if isinstance(entry, ReplyEntry)]
            labels = [(entry, translator(entry.text_key, locale)) for entry in entries]
            for index, (entry, label) in enumerate(labels):
                if not isinstance(cast(object, label), str) or not label:
                    raise ConfigurationError("Reply translations must be nonempty text")
                for other, other_label in labels[index + 1 :]:
                    if label == other_label and _overlap(entry, other):
                        raise ConfigurationError("Reply labels are ambiguous within a scope")

    def match_reply(
        self,
        text: str,
        current_node: str | None,
        *,
        current_locale: str,
        installed_locale: str | None = None,
        translator: Translator,
        allow_scoped: bool = True,
    ) -> MatchedEntry | None:
        locales = tuple(dict.fromkeys((current_locale, installed_locale or current_locale)))
        candidates: list[ReplyEntry] = []
        labels: dict[str, str] = {}
        for entry in self.entries:
            if not isinstance(entry, ReplyEntry) or not _allowed(entry, current_node):
                continue
            if not allow_scoped and not entry.global_action:
                continue
            translated = [translator(entry.text_key, locale) for locale in locales]
            for label in translated:
                if not isinstance(cast(object, label), str) or not label:
                    raise ConfigurationError("Reply translations must be nonempty text")
                if label in labels and labels[label] != entry.id:
                    raise ConfigurationError("Reply labels are ambiguous within the active scope")
                labels[label] = entry.id
            if text in translated:
                candidates.append(entry)
        if len(candidates) > 1:
            raise ConfigurationError("Reply labels are ambiguous within the active scope")
        return MatchedEntry(candidates[0], candidates[0].params, "reply") if candidates else None
