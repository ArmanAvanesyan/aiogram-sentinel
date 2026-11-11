"""Validate an exact companion release before Trusted Publishing.

Run with Python 3.10+ (tomli required on 3.10) against an isolated artifact directory.
This tool never
imports a wheel, extracts an archive, rebuilds artifacts or contacts a service.
"""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 tooling profile
    import tomli as tomllib


TARGETS = frozenset(
    {
        "linux-glibc-x86_64",
        "linux-glibc-aarch64",
        "linux-musl-x86_64",
        "linux-musl-aarch64",
        "macos-x86_64",
        "macos-arm64",
        "windows-amd64",
    }
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name)
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in name
    )


def platform_target(tag: str) -> str:
    if re.fullmatch(r"(?:manylinux_2_17|manylinux2014)_(x86_64|aarch64)", tag):
        return (
            "linux-glibc-aarch64" if tag.endswith("aarch64") else "linux-glibc-x86_64"
        )
    if re.fullmatch(r"musllinux_1_2_(x86_64|aarch64)", tag):
        return "linux-musl-aarch64" if tag.endswith("aarch64") else "linux-musl-x86_64"
    if re.fullmatch(r"macosx_\d+_\d+_(x86_64|arm64)", tag):
        return "macos-arm64" if tag.endswith("arm64") else "macos-x86_64"
    if tag == "win_amd64":
        return "windows-amd64"
    raise ValueError(f"Unexpected wheel platform: {tag}")


def metadata(raw: bytes, name: str, version: str) -> None:
    headers = email.parser.BytesParser().parsebytes(raw)
    require(headers.get_all("Name") == [name], "Distribution metadata name mismatch")
    require(
        headers.get_all("Version") == [version],
        "Distribution metadata version mismatch",
    )
    require(
        headers.get_all("Requires-Python") == [">=3.10"],
        "Unexpected Python requirement",
    )
    require(
        not headers.get_all("Requires-Dist"),
        "Companion must not depend on a base distribution",
    )


def wheel(
    path: Path, name: str, version: str, *, module_name: str | None = None
) -> str:
    parts = path.name.removesuffix(".whl").rsplit("-", 4)
    require(len(parts) == 5, "Unexpected wheel filename/build tag")
    dist, found_version, python, abi, platforms = parts
    require(
        dist == name.replace("-", "_") and found_version == version,
        "Wheel filename identity mismatch",
    )
    require(
        python == "cp310" and abi == "abi3", "Expected CPython 3.10 stable ABI wheel"
    )
    targets = {platform_target(tag) for tag in platforms.split(".")}
    require(len(targets) == 1, "One wheel must identify exactly one platform target")
    module = "_" + name.removesuffix("-native").replace("-", "_") + "_native"
    module_parts = (module_name or module).split(".")
    require(
        all(part.isidentifier() and part.isascii() for part in module_parts),
        "Invalid native import path",
    )
    require(module_parts[-1] == module, "Unexpected native module basename")
    parent = PurePosixPath(*module_parts[:-1])
    allowed_parents = (
        {parent} if len(module_parts) > 1 else {parent, PurePosixPath(module)}
    )
    info_root = f"{name.replace('-', '_')}-{version}.dist-info/"
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate wheel members")
        require(all(safe_name(item) for item in names), "Unsafe wheel member path")
        entries = [item for item in names if item.endswith(".dist-info/METADATA")]
        require(
            entries == [info_root + "METADATA"],
            "Expected exact distribution metadata path",
        )
        metadata(archive.read(entries[0]), name, version)
        extensions = [
            item
            for item in names
            if PurePosixPath(item).name.startswith(module + ".")
            and item.endswith((".so", ".pyd"))
        ]
        require(len(extensions) == 1, "Expected one correctly named native extension")
        extension_parent = PurePosixPath(extensions[0]).parent
        require(
            extension_parent in allowed_parents,
            "Native extension is outside its configured import path",
        )
        if extension_parent != PurePosixPath("."):
            require(
                str(extension_parent / "__init__.py") in names,
                "Native package wrapper is absent",
            )
        descriptors = [item for item in names if item.endswith(".dist-info/WHEEL")]
        require(
            descriptors == [info_root + "WHEEL"], "Expected exact wheel descriptor path"
        )
        headers = email.parser.BytesParser().parsebytes(archive.read(descriptors[0]))
        require(
            headers.get("Root-Is-Purelib") == "false",
            "Native wheel incorrectly marked pure Python",
        )
        require(
            set(headers.get_all("Tag", []))
            == {f"cp310-abi3-{p}" for p in platforms.split(".")},
            "Wheel descriptor tags disagree with filename",
        )
    return targets.pop()


def sdist(path: Path, name: str, version: str) -> None:
    require(
        path.name == f"{name.replace('-', '_')}-{version}.tar.gz",
        "Unexpected source archive filename",
    )
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        require(len(names) == len(set(names)), "Duplicate source archive members")
        require(all(safe_name(item) for item in names), "Unsafe source archive path")
        require(
            all(member.isfile() or member.isdir() for member in members),
            "Source archive contains links or special files",
        )
        roots = {PurePosixPath(item).parts[0] for item in names}
        require(len(roots) == 1, "Expected one source archive root")
        root = roots.pop()
        require(
            {
                root + "/pyproject.toml",
                root + "/Cargo.toml",
                root + "/Cargo.lock",
            }.issubset(names),
            "Source archive lacks locked native build inputs",
        )
        info = archive.extractfile(root + "/PKG-INFO")
        require(info is not None, "Source archive metadata absent")
        assert info is not None
        metadata(info.read(), name, version)


def verify(
    directory: Path,
    *,
    root_project: Path,
    native_project: Path,
    tag: str,
    manifest_sha256: str,
) -> dict[str, object]:
    base = tomllib.loads(root_project.read_text())["project"]
    native_document = tomllib.loads(native_project.read_text())
    native = native_document["project"]
    module_name = native_document.get("tool", {}).get("maturin", {}).get("module-name")
    name, version = base["name"] + "-native", base["version"]
    require(
        native["name"] == name and native["version"] == version,
        "Base/native project mismatch",
    )
    require(tag == "native-v" + version, "Native release tag mismatch")
    require(
        re.fullmatch(r"[a-f0-9]{64}", manifest_sha256) is not None,
        "Invalid independent manifest digest",
    )
    manifest = directory / "SHA256SUMS"
    require(
        hashlib.sha256(manifest.read_bytes()).hexdigest() == manifest_sha256,
        "Checksum manifest is not the independently reviewed manifest",
    )
    declared: dict[str, str] = {}
    for line in manifest.read_text().splitlines():
        parts = line.split()
        require(len(parts) == 2, "Malformed checksum entry")
        digest, filename = parts
        require(
            re.fullmatch(r"[a-f0-9]{64}", digest) is not None, "Invalid artifact digest"
        )
        require(
            Path(filename).name == filename and filename not in declared,
            "Unsafe or duplicate checksum filename",
        )
        declared[filename] = digest
    require(
        {p.name for p in directory.iterdir()} == set(declared) | {"SHA256SUMS"},
        "Unexpected or missing release artifacts",
    )
    require(
        len(declared) == len(TARGETS) + 1,
        "Expected seven native wheels and one source archive",
    )
    coverage: set[str] = set()
    source_count = 0
    for filename, digest in declared.items():
        artifact = directory / filename
        require(
            artifact.is_file() and not artifact.is_symlink(),
            "Artifact is not a regular file",
        )
        require(
            hashlib.sha256(artifact.read_bytes()).hexdigest() == digest,
            "Artifact differs from reviewed checksum",
        )
        if filename.endswith(".whl"):
            target = wheel(artifact, name, version, module_name=module_name)
            require(target not in coverage, "Duplicate native wheel target")
            coverage.add(target)
        else:
            sdist(artifact, name, version)
            source_count += 1
    require(
        coverage == TARGETS and source_count == 1,
        "Native platform coverage is incomplete",
    )
    return {
        "project": name,
        "version": version,
        "targets": sorted(coverage),
        "manifest_sha256": manifest_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--root-project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument(
        "--native-project", type=Path, default=Path("native/pyproject.toml")
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                args.directory,
                root_project=args.root_project,
                native_project=args.native_project,
                tag=args.tag,
                manifest_sha256=args.manifest_sha256,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
