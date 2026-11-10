"""Check an installed base artifact without optional infrastructure dependencies."""

from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path

import aiogram_sentinel
from aiogram_sentinel import SentinelConfig
from aiogram_sentinel.exceptions import ConfigurationError
from aiogram_sentinel.storage.factory import build_infra

assert aiogram_sentinel.__version__ == version("aiogram-sentinel")
assert Path(aiogram_sentinel.__file__).with_name("py.typed").is_file()
assert find_spec("redis") is None
assert find_spec("sentry_sdk") is None
build_infra(SentinelConfig())
try:
    build_infra(SentinelConfig(backend="redis"))
except ConfigurationError as error:
    assert "aiogram-sentinel[redis]" in str(error)
else:
    raise AssertionError("Redis selection must explain its missing extra")
print("Installed base artifact: version, typing, memory and optional imports verified")
