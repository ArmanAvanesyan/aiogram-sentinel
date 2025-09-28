#!/usr/bin/env python3
"""Check that package version matches the git tag."""

import os
import re
import sys
from pathlib import Path


def get_version_from_package() -> str:
    """Get version from package __init__.py or version.py."""
    package_dir = Path("src/aiogram_sentinel")

    # Try version.py first
    version_file = package_dir / "version.py"
    if version_file.exists():
        with open(version_file) as f:
            content = f.read()
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)

    # Try __init__.py
    init_file = package_dir / "__init__.py"
    if init_file.exists():
        with open(init_file) as f:
            content = f.read()
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)

    raise RuntimeError("Could not find __version__ in package files")


def get_version_from_pyproject() -> str:
    """Get version from pyproject.toml."""
    pyproject_file = Path("pyproject.toml")
    if not pyproject_file.exists():
        raise RuntimeError("pyproject.toml not found")

    with open(pyproject_file) as f:
        content = f.read()
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)

    raise RuntimeError("Could not find version in pyproject.toml")


def get_tag_version() -> str:
    """Get version from git tag."""
    ref = os.environ.get("GITHUB_REF", "")
    if not ref.startswith("refs/tags/v"):
        raise RuntimeError(f"Not a version tag: {ref}")

    # Extract version from tag (remove 'refs/tags/v' prefix)
    tag_version = ref[11:]  # Remove 'refs/tags/v'

    # Validate version format
    if not re.match(r"^\d+\.\d+\.\d+$", tag_version):
        raise RuntimeError(f"Invalid version format: {tag_version}")

    return tag_version


def main() -> None:
    """Main function."""
    try:
        # Get versions from different sources
        package_version = get_version_from_package()
        pyproject_version = get_version_from_pyproject()
        tag_version = get_tag_version()

        print(f"Package version: {package_version}")
        print(f"PyProject version: {pyproject_version}")
        print(f"Tag version: {tag_version}")

        # Check if all versions match
        if package_version != tag_version:
            print(
                f"ERROR: Package version ({package_version}) does not match tag version ({tag_version})"
            )
            sys.exit(1)

        if pyproject_version != tag_version:
            print(
                f"ERROR: PyProject version ({pyproject_version}) does not match tag version ({tag_version})"
            )
            sys.exit(1)

        print("✅ All versions match!")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
