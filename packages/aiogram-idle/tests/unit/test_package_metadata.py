"""Distribution contracts shared by base and optional installations."""

from importlib.metadata import metadata, version
from importlib.resources import files

import aiogram_idle


def test_runtime_version_uses_distribution_metadata() -> None:
    assert aiogram_idle.__version__ == version("aiogram-idle")


def test_distribution_contains_typed_marker() -> None:
    assert files("aiogram_idle").joinpath("py.typed").is_file()


def test_base_runtime_does_not_require_optional_backends() -> None:
    requirements = metadata("aiogram-idle").get_all("Requires-Dist") or []
    base = [requirement.lower() for requirement in requirements if "extra ==" not in requirement]
    assert any(requirement.startswith("aiogram") for requirement in base)
    assert not any(requirement.startswith(("redis", "aiogram-nav")) for requirement in base)
