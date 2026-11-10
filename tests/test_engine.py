"""Engine selection is explicit, versioned and cannot silently fall back."""

from types import SimpleNamespace

import pytest

from aiogram_nav import ConfigurationError, ManualClock, NavigationConfig, NavigationRegistry, Node
from aiogram_nav.codec import decode, encode
from aiogram_nav.engine import native_core
from aiogram_nav.storage.memory import MemoryNavigationRepository
from aiogram_nav.storage.state import fingerprint
from tests.test_storage import KEY, enter


def test_missing_native_is_configuration_error(monkeypatch):
    native_core.cache_clear()

    def absent(name):
        raise ModuleNotFoundError(name)

    with monkeypatch.context() as patch:
        patch.setattr("aiogram_nav.engine.importlib.import_module", absent)
        with pytest.raises(ConfigurationError, match="requires"):
            NavigationConfig(engine="rust")
    native_core.cache_clear()


def test_partial_or_wrong_abi_rejected_before_backend_creation(monkeypatch):
    native_core.cache_clear()
    with monkeypatch.context() as patch:
        patch.setattr(
            "aiogram_nav.engine.importlib.import_module",
            lambda name: SimpleNamespace(API_VERSION=1, ENGINE_VERSION="0.3.0"),
        )
        with pytest.raises(ConfigurationError, match="ABI"):
            MemoryNavigationRepository(config=NavigationConfig(engine="rust"))
    native_core.cache_clear()


def native():
    pytest.importorskip("aiogram_nav_native")
    return native_core()


def test_native_codec_and_fingerprint_match_python():
    native()
    values = [
        None,
        True,
        2**150,
        -(2**150),
        -0.0,
        1.23456789012345,
        {"hy": "Հայերեն", "a": (1, 2)},
        {"a": "😀"},
    ]
    for value in values:
        raw = encode(value, schema_version=3)
        assert decode(raw, engine="rust") == decode(raw)
        assert fingerprint(value, engine="rust") == fingerprint(value)
    for raw in [
        '{"schema_version":3,"schema_version":3,"value":1}',
        '{"schema_version":3,"value":NaN}',
    ]:
        with pytest.raises(ConfigurationError):
            decode(raw, engine="rust")


async def test_native_backend_state_and_history_match_python():
    native()
    configs = [NavigationConfig(engine=name) for name in ("python", "rust")]
    repos = [
        MemoryNavigationRepository(clock=ManualClock(1000), config=config) for config in configs
    ]
    for i in range(30):
        results = [
            (await enter(repo, node=f"n{i % 3}", op=f"operation-{i}"))[1].snapshot for repo in repos
        ]
        a, b = results
        assert (
            a.node_id,
            a.params,
            a.history,
            a.nav_revision,
            a.activity_revision,
            a.entered_at,
            a.last_activity_at,
        ) == (
            b.node_id,
            b.params,
            b.history,
            b.nav_revision,
            b.activity_revision,
            b.entered_at,
            b.last_activity_at,
        )
    assert len(repos[0]._records[KEY].expiry_heap) == 30


def test_native_registry_errors_and_targets_match_python():
    native()
    nodes = [
        Node("main", renderer="screen"),
        Node("child", parent="main", renderer="screen", cancel_to="main"),
    ]
    python = NavigationRegistry(roots={"main"}, nodes=nodes)
    rust = NavigationRegistry(roots={"main"}, nodes=nodes, engine="rust")
    assert rust.root_for("child") == python.root_for("child")
    assert rust.cancel_target("child") == python.cancel_target("child")
    assert rust.ancestors("child") == python.ancestors("child")
    with pytest.raises(ConfigurationError):
        NavigationRegistry(
            roots={"main"}, nodes=[*nodes, Node("orphan", parent="missing")], engine="rust"
        )
