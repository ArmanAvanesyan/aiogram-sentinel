#!/usr/bin/env python3
"""
Version consistency checker for aiogram-cmds.

This script validates version consistency between:
- Package version (src/aiogram_cmds/version.py)
- PyProject version (pyproject.toml)
- Git tag version (from GITHUB_REF)

Usage:
    python tools/check_version_tag.py

Exit codes:
    0 - All versions are consistent
    1 - Version mismatch found
    2 - Error reading version information
"""

import os
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


def get_package_version() -> str | None:
    """Get version from package version.py file."""
    try:
        version_file = Path("src/aiogram_cmds/version.py")
        if not version_file.exists():
            print(f"❌ Version file not found: {version_file}")
            return None

        content = version_file.read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)

        if not match:
            print(f"❌ Could not find __version__ in {version_file}")
            return None

        version = match.group(1)
        print(f"📦 Package version: {version}")
        return version

    except Exception as e:
        print(f"❌ Error reading package version: {e}")
        return None


def get_pyproject_version() -> str | None:
    """Get version from pyproject.toml file."""
    try:
        pyproject_file = Path("pyproject.toml")
        if not pyproject_file.exists():
            print(f"❌ PyProject file not found: {pyproject_file}")
            return None

        content = pyproject_file.read_text(encoding="utf-8")
        data = tomllib.loads(content)

        version = data.get("project", {}).get("version")
        if not version:
            print(f"❌ Could not find project.version in {pyproject_file}")
            return None

        print(f"📋 PyProject version: {version}")
        return version

    except Exception as e:
        print(f"❌ Error reading PyProject version: {e}")
        return None


def get_git_tag_version() -> str | None:
    """Get version from git tag (GITHUB_REF environment variable)."""
    try:
        github_ref = os.getenv("GITHUB_REF")
        if not github_ref:
            print("ℹ️  GITHUB_REF not set, skipping git tag check")
            return None

        # Extract version from refs/tags/v1.2.3 format
        if github_ref.startswith("refs/tags/"):
            tag = github_ref[10:]  # Remove "refs/tags/" prefix

            # Remove 'v' prefix if present
            if tag.startswith("v"):
                version = tag[1:]
            else:
                version = tag

            print(f"🏷️  Git tag version: {version}")
            return version
        else:
            print(f"ℹ️  GITHUB_REF is not a tag: {github_ref}")
            return None

    except Exception as e:
        print(f"❌ Error reading git tag version: {e}")
        return None


def normalize_version(version: str) -> str:
    """Normalize version string for comparison."""
    # Remove any leading/trailing whitespace
    version = version.strip()

    # Remove 'v' prefix if present
    if version.startswith("v"):
        version = version[1:]

    return version


def check_version_consistency() -> int:
    """Check version consistency across all sources."""
    print("🔍 Checking version consistency...")
    print()

    # Get versions from all sources
    package_version = get_package_version()
    pyproject_version = get_pyproject_version()
    git_tag_version = get_git_tag_version()

    print()

    if package_version is None or pyproject_version is None:
        print("❌ Both package and project versions must be readable")
        return 2

    # Normalize versions for comparison
    normalized_versions = {}
    if package_version:
        normalized_versions["package"] = normalize_version(package_version)
    if pyproject_version:
        normalized_versions["pyproject"] = normalize_version(pyproject_version)
    if git_tag_version:
        normalized_versions["git_tag"] = normalize_version(git_tag_version)

    # Check consistency
    unique_versions = set(normalized_versions.values())

    if len(unique_versions) == 1:
        print("✅ All versions are consistent!")
        print(f"   Version: {list(unique_versions)[0]}")
        return 0
    else:
        print("❌ Version mismatch found!")
        print()
        for source, version in normalized_versions.items():
            print(f"   {source}: {version}")
        print()
        print("Please ensure all versions match before releasing.")
        return 1


def main() -> int:
    """Main function."""
    print("aiogram-cmds Version Consistency Checker")
    print("=" * 50)
    print()

    try:
        return check_version_consistency()

    except KeyboardInterrupt:
        print("\n⏹️  Check interrupted by user")
        return 2

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
