"""Installed metadata is the authority for the package version."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aiogram-nav")
except PackageNotFoundError:
    # A bare source checkout has no distribution version until it is installed.
    # Do not duplicate the release version or guess a published version here.
    __version__ = "0+unknown"
