"""Distribution contracts independent of the optional backends."""

from __future__ import annotations

import importlib.metadata
import runpy
from pathlib import Path

import aiogram_nav


def test_runtime_version_comes_from_installed_metadata():
    assert aiogram_nav.__version__ == importlib.metadata.version("aiogram-nav")


def test_installed_package_retains_typed_marker():
    assert Path(aiogram_nav.__file__).with_name("py.typed").is_file()


def test_uninstalled_source_has_explicit_unknown_version(monkeypatch):
    def absent(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", absent)
    result = runpy.run_path(str(Path(aiogram_nav.__file__).with_name("version.py")))
    assert result["__version__"] == "0+unknown"
