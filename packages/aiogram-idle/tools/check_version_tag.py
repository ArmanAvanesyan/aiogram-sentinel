"""Check project, installed and runtime versions; optionally verify a Git tag."""

from __future__ import annotations

import os
from importlib.metadata import version
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 developer environments.
    import tomli as tomllib


def main() -> None:
    from aiogram_idle import __version__

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected = project["version"]
    observed = {"runtime": __version__, "distribution": version(project["name"])}
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/"):
        observed["tag"] = (
            ref.removeprefix("refs/tags/").removeprefix("aiogram-idle-").removeprefix("v")
        )
    for label, value in observed.items():
        if value != expected:
            raise SystemExit(f"{label} version {value!r} differs from project version {expected!r}")
    print(f"Project, runtime, distribution and any supplied tag agree: {expected}")


if __name__ == "__main__":
    main()
