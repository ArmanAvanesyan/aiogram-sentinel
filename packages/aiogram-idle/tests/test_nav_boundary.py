"""The optional adapter rejects unsupported peer versions without changing core imports."""

import importlib

import pytest

nav = pytest.importorskip("aiogram_nav")


def test_optional_integration_rejects_incompatible_navigation_version(monkeypatch):
    import aiogram_idle.integrations.nav as integration

    original = nav.__version__
    try:
        monkeypatch.setattr(nav, "__version__", "0.4.0")
        with pytest.raises(ImportError, match="aiogram-nav>=0.3.0,<0.4"):
            importlib.reload(integration)
    finally:
        monkeypatch.setattr(nav, "__version__", original)
        importlib.reload(integration)


def test_integration_rejects_backend_without_atomic_component_capability():
    from aiogram_nav import NavigationRegistry, Node

    from aiogram_idle.errors import ConfigurationError
    from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
    from aiogram_idle.policies import ExemptPolicy, IdlePolicies
    from aiogram_idle.runtime import IdleRuntime
    from aiogram_idle.storage.memory import MemoryIdleBackend
    from tests.runtime_helpers import Adapter, Presenter

    backend = MemoryIdleBackend()
    backend.capabilities = frozenset({"opaque_components"})
    runtime = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"none": ExemptPolicy()}),
        adapters={"app": Adapter()},
        presenter=Presenter(backend.clock),
    )
    registry = NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="text")])
    with pytest.raises(ConfigurationError, match="atomic"):
        NavigationIntegration(
            idle=runtime, registry=registry, policies=NodePolicies(default="none")
        )
    assert runtime.component_finalizer is None and runtime.component_recovery is None
    assert "aiogram_nav" not in runtime.adapters


async def test_combined_shutdown_drains_worker_before_closing_shared_fsm(monkeypatch):
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    from aiogram_idle.storage.memory import MemoryIdleBackend
    from tests.test_nav_atomic_recovery import build

    order = []

    class Storage(MemoryStorage):
        async def close(self):
            order.append("fsm-close")

    idle, integration, navigation, _ = build(MemoryIdleBackend())
    dispatcher = Dispatcher(storage=Storage())

    async def stop():
        order.append("idle-drain")

    monkeypatch.setattr(idle, "stop", stop)
    integration.install(dispatcher, navigation=navigation)
    await dispatcher.emit_shutdown()
    assert order == ["idle-drain", "fsm-close"]
