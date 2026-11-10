"""Check standalone wheel/sdist installs without optional Redis or navigation."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SMOKE = """
import importlib.util
from importlib.metadata import version
from importlib.resources import files
import aiogram_idle
from aiogram_idle import IdleConfig, IdleRuntime, MemoryIdleBackend

assert aiogram_idle.__version__ == version("aiogram-idle")
assert files("aiogram_idle").joinpath("py.typed").is_file()
assert not IdleConfig().enabled
assert MemoryIdleBackend is not None and IdleRuntime is not None
assert importlib.util.find_spec("redis") is None
assert importlib.util.find_spec("aiogram_nav") is None
print("Standalone artifact:", aiogram_idle.__version__)
"""


def check(artifact: Path, *, peers: tuple[Path, ...] = ()) -> None:
    artifact = artifact.resolve(strict=True)
    if not (artifact.name.endswith(".whl") or artifact.name.endswith(".tar.gz")):
        raise ValueError(f"Expected a wheel or source distribution: {artifact.name}")
    with tempfile.TemporaryDirectory(prefix="aiogram-idle-artifact-") as directory:
        root = Path(directory)
        environment = root / "env"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        candidates = [str(peer.resolve(strict=True)) for peer in peers]
        if candidates:
            print("Explicit candidate dependencies:", candidates, flush=True)
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(artifact), *candidates],
            check=True,
        )
        subprocess.run([str(python), "-I", "-c", SMOKE], cwd=root, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument(
        "--peer",
        action="append",
        type=Path,
        default=[],
        help="Explicit candidate wheel/source dependency; omitted means registry-only",
    )
    args = parser.parse_args()
    for artifact in args.artifacts:
        check(artifact, peers=tuple(args.peer))


if __name__ == "__main__":
    main()
