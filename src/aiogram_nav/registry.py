"""Immutable structural navigation registry with explicit target semantics."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping
from types import MappingProxyType
from typing import cast

from .engine import EngineName, NativeRegistry, native_core, require_engine
from .errors import ConfigurationError, InvalidParameters, NodeNotFound
from .json import JsonObject, freeze_object
from .models import Node


class NavigationRegistry:
    def __init__(
        self,
        *,
        roots: Collection[str],
        nodes: Iterable[Node],
        migrations: Mapping[str, str] | None = None,
        safe_root: str | None = None,
        engine: EngineName = "python",
    ) -> None:
        require_engine(engine)
        self.engine = engine
        self._native: NativeRegistry | None = None
        items = tuple(nodes)
        if any(not isinstance(cast(object, node), Node) for node in items):
            raise ConfigurationError("Registry accepts Node values only")
        index = {node.id: node for node in items}
        if len(index) != len(items):
            raise ConfigurationError("Node IDs must be unique")
        self._nodes: Mapping[str, Node] = MappingProxyType(index)
        self._roots = frozenset(roots)
        self._migrations: Mapping[str, str] = MappingProxyType(dict(migrations or {}))
        self._safe_root = safe_root
        self._root_ids: dict[str, str] = {}
        self._cancel_targets: dict[str, str] = {}
        if engine == "rust":
            try:
                self._native = native_core().Registry(
                    json.dumps(
                        {
                            "roots": sorted(self.roots),
                            "nodes": [
                                dict(
                                    id=node.id,
                                    parent=node.parent,
                                    renderer=node.renderer,
                                    back_to=node.back_to,
                                    cancel_to=node.cancel_to,
                                )
                                for node in items
                            ],
                            "migrations": dict(self.migrations),
                            "safe_root": self.safe_root,
                        }
                    )
                )
            except ValueError as error:
                raise ConfigurationError(str(error)) from error
        self.validate()

    def with_engine(self, engine: EngineName) -> NavigationRegistry:
        if engine == self.engine:
            return self
        return NavigationRegistry(
            roots=self.roots,
            nodes=self.nodes.values(),
            migrations=self.migrations,
            safe_root=self.safe_root,
            engine=engine,
        )

    @property
    def nodes(self) -> Mapping[str, Node]:
        return self._nodes

    @property
    def roots(self) -> frozenset[str]:
        return self._roots

    @property
    def migrations(self) -> Mapping[str, str]:
        return self._migrations

    @property
    def safe_root(self) -> str | None:
        return self._safe_root

    def get(self, node_id: str) -> Node:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise NodeNotFound("Navigation node is not registered") from exc

    def resolve(self, node_id: str) -> Node:
        """Resolve an explicit migration, then an explicitly configured safe root."""
        if node_id in self._nodes:
            return self._nodes[node_id]
        target = self._migrations.get(node_id, self._safe_root)
        if target is None:
            raise NodeNotFound("Persisted navigation node requires migration")
        return self.get(target)

    def ancestors(self, node_id: str) -> tuple[Node, ...]:
        if self._native is not None:
            self.get(node_id)
            return tuple(self.get(item) for item in self._native.ancestors(node_id))
        node = self.get(node_id)
        result: list[Node] = []
        while True:
            result.append(node)
            if node.parent is None:
                break
            node = self.get(node.parent)
        return tuple(result)

    def root_for(self, node_id: str) -> str:
        self.get(node_id)
        return (
            self._native.root_for(node_id) if self._native is not None else self._root_ids[node_id]
        )

    def back_target(self, node_id: str) -> str | None:
        return self.get(node_id).back_to

    def cancel_target(self, node_id: str) -> str:
        self.get(node_id)
        return (
            self._native.cancel_target(node_id)
            if self._native is not None
            else self._cancel_targets[node_id]
        )

    def validate_params(
        self, node_id: str, params: Mapping[str, object] | None = None
    ) -> JsonObject:
        node = self.get(node_id)
        frozen = freeze_object({} if params is None else params)
        if node.validator is None:
            return frozen
        try:
            return freeze_object(node.validator(frozen))
        except InvalidParameters:
            raise
        except Exception as exc:
            raise InvalidParameters("Node parameter validation failed") from exc

    def validate(self, renderers: Collection[str] | None = None) -> None:
        if self._native is not None:
            if renderers is not None and any(
                node.renderer is not None and node.renderer not in renderers
                for node in self._nodes.values()
            ):
                raise ConfigurationError("A registry renderer is unavailable")
            return
        if not self._roots:
            raise ConfigurationError("At least one navigation root is required")
        if not self._roots <= self._nodes.keys():
            raise ConfigurationError("Every root must be registered")
        for root in self._roots:
            if self._nodes[root].parent is not None or self._nodes[root].renderer is None:
                raise ConfigurationError("Roots must be parentless renderable nodes")
        for node in self._nodes.values():
            if node.parent is None and node.id not in self._roots:
                raise ConfigurationError("Every node must reach a configured root")
            for target in (node.back_to, node.cancel_to):
                if target is not None and (
                    target not in self._nodes or self._nodes[target].renderer is None
                ):
                    raise ConfigurationError("Navigation target must exist and be renderable")
            if (
                renderers is not None
                and node.renderer is not None
                and node.renderer not in renderers
            ):
                raise ConfigurationError("A registry renderer is unavailable")
        if not self._root_ids:
            self._index_graph()
        if self._safe_root is not None and self._safe_root not in self._roots:
            raise ConfigurationError("safe_root must be a configured root")
        for source, target in self._migrations.items():
            if (
                source in self._nodes
                or not source
                or target not in self._nodes
                or self._nodes[target].renderer is None
            ):
                raise ConfigurationError(
                    "Migrations must explicitly map missing IDs to renderable nodes"
                )

    def _index_graph(self) -> None:
        # Each edge is visited once. No recursive DFS or quadratic ancestor cache.
        for node in self._nodes.values():
            path: list[Node] = []
            seen: set[str] = set()
            current = node
            while current.id not in self._root_ids:
                if current.id in seen:
                    raise ConfigurationError("Navigation parent graph contains a cycle")
                seen.add(current.id)
                path.append(current)
                if current.parent is None:
                    root = current.id
                    inherited = root
                    break
                if current.parent not in self._nodes:
                    raise ConfigurationError("Navigation parent does not exist")
                current = self._nodes[current.parent]
            else:
                root = self._root_ids[current.id]
                inherited = self._cancel_targets[current.id]
            for ancestor in reversed(path):
                inherited = ancestor.cancel_to or inherited
                self._root_ids[ancestor.id] = root
                self._cancel_targets[ancestor.id] = inherited

    def snapshot(self) -> tuple[tuple[str, str | None, str | None, str | None, str | None], ...]:
        """Stable reviewable registry structure, independent of labels/numbering."""
        return tuple(
            (node.id, node.parent, node.renderer, node.back_to, node.cancel_to)
            for node in self._nodes.values()
        )
