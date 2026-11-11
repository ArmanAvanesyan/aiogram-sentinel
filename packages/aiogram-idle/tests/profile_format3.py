"""Opt-in format-three factories for the existing behavioral test corpus.

Load explicitly: pytest -p tests.profile_format3 --idle-profile-engine python ...
Only constructor defaults are supplied. No storage-format activation guard,
coordinator, server response or application effect is bypassed.
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

# These are behavioral suites, rather than legacy-wire decoder/activation tests.
CORE_CORPUS = (
    "tests/test_memory.py",
    "tests/test_activity_and_observability.py",
    "tests/test_audit_scale.py",
    "tests/test_audit_storage.py",
    "tests/test_effect_scope_review.py",
    "tests/test_correctness_021.py",
    "tests/test_redis_admin.py",
    "tests/test_redis_deployment.py",
    "tests/test_memory_edges.py",
    "tests/test_audit_engine.py",
    "tests/test_audit_recovery.py",
    "tests/test_audit_fsm.py",
    "tests/test_timeout_audit.py",
    "tests/test_custom_isolation.py",
    "tests/test_managed_shutdown.py",
    "tests/test_telegram.py",
    "tests/test_telegram_failures.py",
    "tests/unit/test_runtime.py",
    "tests/unit/test_runtime_edges.py",
    "tests/unit/test_recovery_regressions.py",
    "tests/unit/test_lookup_audit.py",
    "tests/test_redis_backend.py",
    "tests/test_redis_recovery.py",
    "tests/test_redis_atomicity.py",
    "tests/test_redis_commit_audit.py",
    "tests/test_redis_queue_audit.py",
    "tests/test_redis_effect_audit.py",
    "tests/test_redis_coord.py",
    "tests/test_redis_dispatcher.py",
    "tests/test_redis_fsm_audit.py",
    "tests/test_redis_presentation.py",
    "tests/test_native_backend.py",
    "tests/test_external_sessions.py",
    "tests/test_redis_external_sessions.py",
)
COMBINED_CORPUS = (
    "tests/test_nav_runtime.py",
    "tests/test_nav_boundary.py",
    "tests/test_nav_correctness_021.py",
    "tests/test_nav_external_sessions.py",
    "tests/test_nav_atomic_recovery.py",
    "tests/test_nav_matrix.py",
    "tests/test_nav_manual_application.py",
    "tests/test_nav_reply_restore.py",
    "tests/test_nav_review_fsm.py",
    "tests/test_nav_review_policies.py",
    "tests/test_nav_review_recovery.py",
    "tests/test_nav_projection.py",
    "tests/test_component_transactions.py",
    "tests/test_component_ownership.py",
    "tests/test_component_review.py",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("idle-format3")
    group.addoption("--idle-profile-engine", choices=("python", "rust"), default="python")
    group.addoption("--idle-profile-manifest", type=Path, default=None)
    group.addoption("--nav-profile-engine", choices=("python", "rust"), default=None)


def pytest_report_header(config: pytest.Config) -> str:
    return "idle profile: explicit fresh storage_format=3, engine=" + config.getoption(
        "idle_profile_engine"
    )


def _factories(engine: str) -> tuple[list[tuple[object, str, object]], Callable[..., Any]]:
    from aiogram_idle.config import IdleConfig
    from aiogram_idle.engines import require_engine
    from aiogram_idle.storage.memory import MemoryIdleBackend
    from aiogram_idle.storage.redis import RedisIdleBackend

    require_engine(engine)
    originals: list[tuple[object, str, object]] = []
    config_init = IdleConfig.__init__

    @functools.wraps(config_init)
    def configuration(self: Any, *args: Any, **kwargs: Any) -> None:
        explicit = bool(args) or "engine" in kwargs
        if not args:
            kwargs.setdefault("engine", engine)
        config_init(self, *args, **kwargs)
        object.__setattr__(self, "_test_profile_explicit_engine", explicit)

    originals.append((IdleConfig, "__init__", config_init))
    IdleConfig.__init__ = configuration

    def factory(original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def construct(self: Any, *args: Any, **kwargs: Any) -> None:
            if kwargs.get("storage_format") is None:
                kwargs["storage_format"] = 3
            config = kwargs.get("config")
            if config is not None and not getattr(config, "_test_profile_explicit_engine", False):
                kwargs["config"] = dataclasses.replace(config, engine=engine)
            original(self, *args, **kwargs)

        return construct

    for cls in (MemoryIdleBackend, RedisIdleBackend):
        original = cls.__init__
        originals.append((cls, "__init__", original))
        cls.__init__ = factory(original)
    return originals, configuration


def _navigation_factories(engine: str) -> list[tuple[object, str, object]]:
    from aiogram_nav import NavigationConfig, NavigationRegistry
    from aiogram_nav.engine import require_engine

    require_engine(engine)
    originals = []
    for owner in (NavigationConfig, NavigationRegistry):
        original = owner.__init__

        @functools.wraps(original)
        def construct(self, *args, _original=original, **kwargs):
            kwargs.setdefault("engine", engine)
            _original(self, *args, **kwargs)

        originals.append((owner, "__init__", original))
        owner.__init__ = construct
    return originals


def install_subprocess_profile() -> None:
    """Use the same explicit factories in a test's real killed/crashed child."""
    if os.environ.get("AIOGRAM_IDLE_TEST_PROFILE_ACTIVE") == "1":
        _factories(os.environ.get("AIOGRAM_IDLE_TEST_PROFILE_ENGINE", "python"))
        if os.environ.get("AIOGRAM_IDLE_TEST_NAV_ENGINE"):
            _navigation_factories(os.environ["AIOGRAM_IDLE_TEST_NAV_ENGINE"])


def _child_command(values: tuple[Any, ...]) -> tuple[Any, ...]:
    if (
        len(values) >= 3
        and str(values[0]) == sys.executable
        and values[1] == "-c"
        and isinstance(values[2], str)
        and "aiogram_idle" in values[2]
    ):
        prefix = "from tests.profile_format3 import install_subprocess_profile; install_subprocess_profile()\n"
        return (*values[:2], prefix + values[2], *values[3:])
    return values


@pytest.fixture(autouse=True)
def explicit_format3_factories(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    engine = request.config.getoption("idle_profile_engine")
    originals, _ = _factories(engine)
    nav_engine = request.config.getoption("nav_profile_engine")
    if nav_engine is not None:
        originals.extend(_navigation_factories(nav_engine))
        monkeypatch.setenv("AIOGRAM_IDLE_TEST_NAV_ENGINE", nav_engine)
    monkeypatch.setenv("AIOGRAM_IDLE_TEST_PROFILE_ACTIVE", "1")
    monkeypatch.setenv("AIOGRAM_IDLE_TEST_PROFILE_ENGINE", engine)
    # Fault tests identify the actual mutation script by SHA; target format 3's
    # real script, retaining their before/after-server-response fault injection.
    from aiogram_idle.storage.cold_scripts import COMMIT_COLD, READ_COLD
    from aiogram_idle.storage.redis_scripts import COMMIT, READ

    # Only test-facing aliases change: production stores and compose functions
    # have already bound their real implementation scripts above.
    script_module = importlib.import_module("aiogram_idle.storage.redis_scripts")
    monkeypatch.setattr(script_module, "COMMIT", COMMIT_COLD)
    monkeypatch.setattr(script_module, "READ", READ_COLD)
    for name, module in tuple(sys.modules.items()):
        if name.startswith("tests.") and module is not None:
            if getattr(module, "COMMIT", None) is COMMIT:
                monkeypatch.setattr(module, "COMMIT", COMMIT_COLD)
            if getattr(module, "READ", None) is READ:
                monkeypatch.setattr(module, "READ", READ_COLD)
    original_run = subprocess.run
    original_exec = asyncio.create_subprocess_exec

    def run(*args: Any, **kwargs: Any):
        if args and isinstance(args[0], (list, tuple)):
            args = (list(_child_command(tuple(args[0]))), *args[1:])
        return original_run(*args, **kwargs)

    async def create_subprocess_exec(*args: Any, **kwargs: Any):
        return await original_exec(*_child_command(args), **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
    try:
        yield
    finally:
        for owner, name, original in reversed(originals):
            setattr(owner, name, original)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # Parametrized script IDs are captured at collection, before the per-test
    # fault alias fixture. Retarget only that test's READ digest, not its effects.
    from aiogram_idle.storage.cold_scripts import READ_COLD
    from aiogram_idle.storage.redis_scripts import READ

    for item in items:
        callspec = getattr(item, "callspec", None)
        if callspec is not None and callspec.params.get("source") == READ:
            callspec.params["source"] = READ_COLD
        if callspec is not None and config.getoption("nav_profile_engine") is not None:
            from aiogram_nav import NavigationConfig

            def defaults(value):
                if isinstance(value, NavigationConfig):
                    return dataclasses.replace(value, engine=config.getoption("nav_profile_engine"))
                if isinstance(value, tuple):
                    return tuple(defaults(part) for part in value)
                return value

            for name, value in tuple(callspec.params.items()):
                callspec.params[name] = defaults(value)


def pytest_collection_finish(session: pytest.Session) -> None:
    destination = session.config.getoption("idle_profile_manifest")
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "storage_format": 3,
                    "engine": session.config.getoption("idle_profile_engine"),
                    "nav_engine": session.config.getoption("nav_profile_engine"),
                    "tests": [item.nodeid for item in session.items],
                    "qualification": False,
                    "note": "Behavioral profile only; legacy schema/activation suites run separately.",
                },
                indent=2,
            )
            + "\n"
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("python", "rust"), default="python")
    parser.add_argument("--combined", action="store_true")
    parser.add_argument(
        "--combined-only",
        action="store_true",
        help="Run integration corpus after the standalone engine profiles",
    )
    parser.add_argument("--nav-engine", choices=("python", "rust"))
    parser.add_argument("--manifest", type=Path)
    args, extra = parser.parse_known_args()
    selection = (
        list(COMBINED_CORPUS)
        if args.combined_only
        else [*CORE_CORPUS, *(COMBINED_CORPUS if args.combined else ())]
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "tests.profile_format3",
        "--idle-profile-engine",
        args.engine,
    ]
    if args.nav_engine:
        command += ["--nav-profile-engine", args.nav_engine]
    if args.manifest:
        command += ["--idle-profile-manifest", str(args.manifest)]
    raise SystemExit(subprocess.call([*command, *selection, *extra]))


if __name__ == "__main__":
    main()
