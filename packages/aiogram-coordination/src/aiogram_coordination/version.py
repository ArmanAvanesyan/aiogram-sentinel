"""Installed metadata is the authoritative package version."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aiogram-coordination")
except PackageNotFoundError:
    __version__ = "0+unknown"
