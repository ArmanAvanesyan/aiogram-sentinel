"""Require package-specific news for public source or packaging changes."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath


def missing_news(paths: list[str]) -> set[str]:
    affected = set()
    documented = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        if len(parts) < 3 or parts[0] != "packages":
            continue
        package, relative = parts[1], parts[2:]
        if relative[0] in {"src", "pyproject.toml"} or relative[:2] in {
            ("native", "src"),
            ("native", "Cargo.toml"),
            ("native", "pyproject.toml"),
        }:
            affected.add(package)
        if (
            relative[0] == "CHANGELOG.md"
            or relative[0] == "CHANGES"
            and relative[-1] not in {"README.md", ".template.rst.jinja2"}
        ):
            documented.add(package)
    return affected - documented


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    paths = subprocess.check_output(
        ["git", "diff", "--name-only", args.base, "HEAD"], text=True
    ).splitlines()
    missing = missing_news(paths)
    if missing:
        raise SystemExit("Missing package changelog/fragment: " + ", ".join(sorted(missing)))
    print("Package-specific changelog coverage verified")
