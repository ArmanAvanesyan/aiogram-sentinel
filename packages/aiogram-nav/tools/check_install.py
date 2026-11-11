"""Verify an installed artifact without relying on a source checkout."""

from __future__ import annotations

import argparse
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path

import aiogram_nav
from aiogram_nav import MemoryNavigationRepository, NavigationRegistry, Node


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis", action="store_true", help="Require the optional Redis client")
    options = parser.parse_args()
    if aiogram_nav.__version__ != version("aiogram-nav"):
        raise RuntimeError("Runtime and installed distribution versions differ")
    if not Path(aiogram_nav.__file__).with_name("py.typed").is_file():
        raise RuntimeError("Installed artifact is missing its typed package marker")
    if find_spec("aiogram_idle") is not None:
        raise RuntimeError("Standalone verification must run without aiogram-idle installed")
    has_redis = find_spec("redis") is not None
    if has_redis != options.redis:
        raise RuntimeError("Redis dependency presence does not match the requested installation")
    registry = NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="text")])
    repository = MemoryNavigationRepository()
    if registry.get("main").id != "main" or "conditional_commits" not in repository.capabilities:
        raise RuntimeError("Memory navigation initialization failed")
    if options.redis:
        from aiogram_nav.storage.redis import RedisNavigationRepository

        if RedisNavigationRepository is None:
            raise RuntimeError("Optional Redis backend is unavailable")
    print("Installed artifact: version, typing, memory and dependency boundaries verified")


if __name__ == "__main__":
    main()
