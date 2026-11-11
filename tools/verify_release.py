"""Verify exactly the reviewed base distributions; never build during publication."""

from __future__ import annotations

import argparse
import hashlib
import re
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

PACKAGES = frozenset(
    {
        "aiogram-kit",
        "aiogram-coordination",
        "aiogram-sentinel",
        "aiogram-cmds",
        "aiogram-nav",
        "aiogram-idle",
    }
)


def verify(root: Path, package: str, tag: str, directory: Path, manifest_sha256: str) -> None:
    if package not in PACKAGES:
        raise ValueError("Unknown distribution")
    project = tomllib.loads((root / "packages" / package / "pyproject.toml").read_text())["project"]
    version = project["version"]
    if project["name"] != package or tag != f"{package}-v{version}":
        raise ValueError("Tag does not match distribution and version")
    if not re.fullmatch(r"[a-f0-9]{64}", manifest_sha256):
        raise ValueError("Expected an independently reviewed SHA256 digest")
    manifest = directory / "SHA256SUMS"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != manifest_sha256:
        raise ValueError("Manifest checksum mismatch")
    normalized = package.replace("-", "_")
    expected = {
        f"{normalized}-{version}-py3-none-any.whl",
        f"{normalized}-{version}.tar.gz",
    }
    if {p.name for p in directory.iterdir()} != expected | {"SHA256SUMS"}:
        raise ValueError("Unexpected release files")
    checked: set[str] = set()
    for line in manifest.read_text().splitlines():
        digest, filename = line.split()
        if (
            filename not in expected
            or filename in checked
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
        ):
            raise ValueError("Unexpected checksum entry")
        path = directory / filename
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Distribution checksum mismatch")
        if filename.endswith(".whl"):
            with zipfile.ZipFile(path) as wheel:
                entries = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
                if len(entries) != 1:
                    raise ValueError("Invalid wheel metadata")
                metadata = wheel.read(entries[0])
        else:
            with tarfile.open(path) as sdist:
                entries = [
                    m
                    for m in sdist.getmembers()
                    if m.name.endswith("/PKG-INFO") and m.name.count("/") == 1
                ]
                if len(entries) != 1:
                    raise ValueError("Invalid sdist metadata")
                stream = sdist.extractfile(entries[0])
                if stream is None:
                    raise ValueError("Missing sdist metadata")
                metadata = stream.read()
        parsed = BytesParser().parsebytes(metadata)
        if parsed["Name"] != package or parsed["Version"] != version:
            raise ValueError("Artifact metadata does not match project")
        checked.add(filename)
    if checked != expected:
        raise ValueError("Missing distribution checksum")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, choices=sorted(PACKAGES))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    verify(
        Path(__file__).resolve().parents[1],
        args.package,
        args.tag,
        args.dist,
        args.manifest_sha256,
    )
