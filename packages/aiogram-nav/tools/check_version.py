"""Check project, installed metadata and optional release tag versions."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import aiogram_nav


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Explicit release tag to compare, for example v0.1.0")
    options = parser.parse_args()
    project = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with project.open("rb") as source:
        expected = tomllib.load(source)["project"]["version"]
    if expected != version("aiogram-nav") or expected != aiogram_nav.__version__:
        raise RuntimeError("Project, installed metadata and runtime versions must agree")
    if options.tag is not None and options.tag != f"v{expected}":
        raise RuntimeError("Release tag does not match the project version")
    print(f"aiogram-nav {expected}: project, metadata and runtime versions agree")


if __name__ == "__main__":
    main()
