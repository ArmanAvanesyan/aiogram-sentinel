"""Structural defaults are explicit; dotted IDs do not imply parents."""

from dataclasses import replace

import pytest

from aiogram_nav.errors import ConfigurationError, InvalidParameters, NodeNotFound
from aiogram_nav.models import Node
from aiogram_nav.registry import NavigationRegistry


def registry():
    return NavigationRegistry(
        roots={"main", "guest"},
        nodes=[
            Node("main", renderer="main"),
            Node("guest", renderer="guest"),
            Node("group", parent="main", cancel_to="main"),
            Node("group.child", parent="group", renderer="child", back_to="main"),
            Node("unrelated.dotted.id", parent="guest", renderer="other"),
        ],
    )


def test_explicit_structural_navigation_and_abstract_groups():
    value = registry()
    assert value.root_for("group.child") == "main"
    assert value.root_for("unrelated.dotted.id") == "guest"
    assert value.cancel_target("group.child") == "main"
    assert value.back_target("group.child") == "main"
    assert [node.id for node in value.ancestors("group.child")] == ["group.child", "group", "main"]
    assert value.get("group").renderer is None
    with pytest.raises(TypeError):
        value.nodes["new"] = Node("new")
    assert value.snapshot()[0] == ("main", None, "main", None, None)


@pytest.mark.parametrize(
    "nodes",
    [
        [Node("main", renderer="x"), Node("main", renderer="y")],
        [Node("main", renderer="x"), Node("child", parent="missing")],
        [Node("main", renderer="x"), Node("a", parent="b"), Node("b", parent="a")],
        [Node("main", renderer="x"), Node("orphan", renderer="y")],
        [Node("main", parent="main", renderer="x")],
        [Node("main")],
        [Node("main", renderer="x", back_to="missing")],
        [Node("main", renderer="x", cancel_to="abstract"), Node("abstract", parent="main")],
    ],
)
def test_invalid_registries_rejected(nodes):
    with pytest.raises(ConfigurationError):
        NavigationRegistry(roots={"main"}, nodes=nodes)


def test_renderer_validation_and_missing_nodes():
    value = registry()
    value.validate(renderers={"main", "guest", "child", "other"})
    with pytest.raises(ConfigurationError):
        value.validate(renderers={"main"})
    with pytest.raises(NodeNotFound):
        value.get("missing")
    with pytest.raises(NodeNotFound):
        value.resolve("missing")


def test_explicit_migration_and_safe_root():
    nodes = list(registry().nodes.values())
    value = NavigationRegistry(
        roots={"main", "guest"}, nodes=nodes, migrations={"old": "group.child"}, safe_root="guest"
    )
    assert value.resolve("old").id == "group.child"
    assert value.resolve("unknown").id == "guest"
    with pytest.raises(ConfigurationError):
        NavigationRegistry(roots={"main", "guest"}, nodes=nodes, safe_root="group.child")
    with pytest.raises(ConfigurationError):
        NavigationRegistry(roots={"main", "guest"}, nodes=nodes, migrations={"old": "group"})


def test_parameter_validator_gets_immutable_object_and_detaches_result():
    def validate(params):
        if params.get("page") not in {1, 2}:
            raise ValueError("bad")
        return {"page": params["page"]}

    value = NavigationRegistry(
        roots={"main"}, nodes=[Node("main", renderer="x", validator=validate)]
    )
    assert value.validate_params("main", {"page": 1}) == {"page": 1}
    with pytest.raises(InvalidParameters):
        value.validate_params("main", {"page": 3})


def test_generated_trees_have_explicit_root_reachability():
    for count in range(1, 40):
        nodes = [Node("main", renderer="x")]
        for n in range(1, count):
            nodes.append(Node(f"n{n}", parent="main" if n < 2 else f"n{n // 2}", renderer="x"))
        value = NavigationRegistry(roots={"main"}, nodes=nodes)
        assert all(value.root_for(node.id) == "main" for node in nodes)
        if count > 2:
            nodes[1] = replace(nodes[1], parent=nodes[-1].id)
            with pytest.raises(ConfigurationError):
                NavigationRegistry(roots={"main"}, nodes=nodes)


def test_deep_registry_uses_iterative_graph_index():
    from aiogram_nav import NavigationRegistry, Node

    nodes = [Node("main", renderer="screen", cancel_to="main")]
    nodes.extend(
        Node(f"n{i}", parent="main" if i == 0 else f"n{i - 1}", renderer="screen")
        for i in range(5000)
    )
    registry = NavigationRegistry(roots={"main"}, nodes=nodes)
    assert registry.root_for("n4999") == "main"
    assert registry.cancel_target("n4999") == "main"
    assert len(registry.ancestors("n4999")) == 5001
