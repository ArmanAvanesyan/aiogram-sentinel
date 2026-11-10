"""Distribution identity and typing marker must agree in installed artifacts."""

from importlib.metadata import version
from importlib.resources import files

import aiogram_cmds
from aiogram_cmds.version import __version__


def test_version_has_one_authoritative_export():
    assert aiogram_cmds.__version__ == __version__ == version("aiogram-cmds")


def test_typing_marker_is_packaged():
    assert files("aiogram_cmds").joinpath("py.typed").is_file()
