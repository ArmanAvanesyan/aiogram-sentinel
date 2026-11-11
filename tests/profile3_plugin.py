"""Explicit qualification profile for the existing fault suite on format three.

Only pytest imports this plugin. Library startup never activates a storage format
implicitly; each isolated test namespace is administratively activated here before
its first application operation. Run separately for each deterministic engine.
"""

import functools
import os


def pytest_addoption(parser):
    parser.addoption("--nav-engine", choices=("python", "rust"), default="python")


def pytest_configure(config):
    from aiogram_nav.config import NavigationConfig
    from aiogram_nav.storage import ledger_scripts, redis_scripts
    from aiogram_nav.storage.redis import RedisNavigationRepository

    engine = config.getoption("--nav-engine")
    config._nav_environment = {
        name: os.environ.get(name)
        for name in ("AIOGRAM_NAV_TEST_ENGINE", "AIOGRAM_NAV_TEST_STORAGE_FORMAT")
    }
    os.environ["AIOGRAM_NAV_TEST_ENGINE"] = engine
    os.environ["AIOGRAM_NAV_TEST_STORAGE_FORMAT"] = "3"
    if engine == "rust":
        from aiogram_nav.engine import require_engine

        require_engine("rust")
    old_config = NavigationConfig.__init__
    old_repository = RedisNavigationRepository.__init__

    @functools.wraps(old_config)
    def configured(self, *args, **kwargs):
        kwargs.setdefault("engine", engine)
        old_config(self, *args, **kwargs)

    @functools.wraps(old_repository)
    def repository(self, *args, **kwargs):
        kwargs.setdefault("storage_format", 3)
        old_repository(self, *args, **kwargs)

    config._nav_restore = (
        NavigationConfig,
        old_config,
        RedisNavigationRepository,
        old_repository,
        redis_scripts,
        redis_scripts.COMMIT,
    )
    NavigationConfig.__init__ = configured
    RedisNavigationRepository.__init__ = repository
    # Existing transport fault injection addresses the active COMMIT script,
    # including imports performed inside individual test functions.
    redis_scripts.COMMIT = ledger_scripts.COMMIT


def pytest_unconfigure(config):
    for name, value in getattr(config, "_nav_environment", {}).items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    restore = getattr(config, "_nav_restore", None)
    if restore is not None:
        cls, constructor, repo, initialize, scripts, commit = restore
        cls.__init__ = constructor
        repo.__init__ = initialize
        scripts.COMMIT = commit
