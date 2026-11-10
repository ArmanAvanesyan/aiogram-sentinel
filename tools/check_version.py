"""Validate project/runtime/tag version consistency without changing files."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from aiogram_coordination import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    args = parser.parse_args()
    expected = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    if expected != __version__:
        raise SystemExit("Project/runtime version mismatch")
    tag = args.tag or (
        os.environ.get("GITHUB_REF_NAME") if os.environ.get("GITHUB_REF_TYPE") == "tag" else None
    )
    if tag is not None and tag != "v" + expected:
        raise SystemExit("Tag/project version mismatch")
    print("Version verified:", expected)


if __name__ == "__main__":
    main()
