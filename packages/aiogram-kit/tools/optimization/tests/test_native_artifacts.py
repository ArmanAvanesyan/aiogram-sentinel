"""Reject native release substitutions before any publisher credentials exist."""

import hashlib
import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "native_artifacts", Path(__file__).parents[1] / "verify_native_artifacts.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PLATFORMS = (
    "manylinux_2_17_x86_64.manylinux2014_x86_64",
    "manylinux_2_17_aarch64.manylinux2014_aarch64",
    "musllinux_1_2_x86_64",
    "musllinux_1_2_aarch64",
    "macosx_10_12_x86_64",
    "macosx_11_0_arm64",
    "win_amd64",
)


def fixture(tmp_path, *, bad_name=False):
    project = tmp_path / "pyproject.toml"
    native = tmp_path / "native.toml"
    project.write_text('[project]\nname="aiogram-nav"\nversion="0.3.0"\n')
    native.write_text('[project]\nname="aiogram-nav-native"\nversion="0.3.0"\n')
    dist = tmp_path / "dist"
    dist.mkdir()
    metadata = (
        "Metadata-Version: 2.1\nName: "
        + ("wrong-native" if bad_name else "aiogram-nav-native")
        + "\nVersion: 0.3.0\nRequires-Python: >=3.10\n\n"
    ).encode()
    for platform in PLATFORMS:
        path = dist / f"aiogram_nav_native-0.3.0-cp310-abi3-{platform}.whl"
        root = "aiogram_nav_native-0.3.0.dist-info/"
        with zipfile.ZipFile(path, "w") as wheel:
            wheel.writestr(root + "METADATA", metadata)
            wheel.writestr(
                root + "WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: false\n"
                + "".join(f"Tag: cp310-abi3-{p}\n" for p in platform.split(".")),
            )
            suffix = ".pyd" if platform == "win_amd64" else ".abi3.so"
            wheel.writestr(
                "_aiogram_nav_native" + suffix,
                b"binary-placeholder-for-structural-tests",
            )
    with tarfile.open(dist / "aiogram_nav_native-0.3.0.tar.gz", "w:gz") as source:
        for filename, body in {
            "pyproject.toml": native.read_bytes(),
            "Cargo.toml": b"[package]",
            "Cargo.lock": b"version=4",
            "PKG-INFO": metadata,
        }.items():
            member = tarfile.TarInfo("aiogram_nav_native-0.3.0/" + filename)
            member.size = len(body)
            source.addfile(member, io.BytesIO(body))
    return project, native, dist


def manifest(dist):
    content = "".join(
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
        for p in sorted(dist.iterdir())
        if p.name != "SHA256SUMS"
    )
    (dist / "SHA256SUMS").write_text(content)
    return hashlib.sha256(content.encode()).hexdigest()


def verify(project, native, dist, digest, tag="native-v0.3.0"):
    return module.verify(
        dist,
        root_project=project,
        native_project=native,
        tag=tag,
        manifest_sha256=digest,
    )


def test_complete_stable_abi_matrix(tmp_path):
    project, native, dist = fixture(tmp_path)
    assert len(verify(project, native, dist, manifest(dist))["targets"]) == 7


def test_wrong_distribution_is_rejected_even_with_valid_hashes(tmp_path):
    project, native, dist = fixture(tmp_path, bad_name=True)
    with pytest.raises(ValueError, match="metadata name"):
        verify(project, native, dist, manifest(dist))


def test_base_tag_is_not_native_authority(tmp_path):
    project, native, dist = fixture(tmp_path)
    with pytest.raises(ValueError, match="tag mismatch"):
        verify(project, native, dist, manifest(dist), "v0.3.0")


def test_independent_digest_cannot_be_replaced(tmp_path):
    project, native, dist = fixture(tmp_path)
    manifest(dist)
    with pytest.raises(ValueError, match="independently reviewed"):
        verify(project, native, dist, "0" * 64)


def test_missing_platform_rejected(tmp_path):
    project, native, dist = fixture(tmp_path)
    next(dist.glob("*win_amd64.whl")).unlink()
    with pytest.raises(ValueError, match="seven native wheels"):
        verify(project, native, dist, manifest(dist))


def test_extra_artifact_rejected(tmp_path):
    project, native, dist = fixture(tmp_path)
    digest = manifest(dist)
    (dist / "unreviewed.whl").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="Unexpected or missing"):
        verify(project, native, dist, digest)


def test_tampering_after_review_rejected(tmp_path):
    project, native, dist = fixture(tmp_path)
    digest = manifest(dist)
    next(dist.glob("*.whl")).write_bytes(b"replaced")
    with pytest.raises(ValueError, match="reviewed checksum"):
        verify(project, native, dist, digest)


def test_companion_version_must_match_base(tmp_path):
    project, native, dist = fixture(tmp_path)
    native.write_text(native.read_text().replace("0.3.0", "0.3.1"))
    with pytest.raises(ValueError, match="Base/native"):
        verify(project, native, dist, manifest(dist))


def test_relocated_extension_cannot_pass_by_basename(tmp_path):
    project, native, dist = fixture(tmp_path)
    target = next(dist.glob("*win_amd64.whl"))
    with zipfile.ZipFile(target) as archive:
        data = {item: archive.read(item) for item in archive.namelist()}
    data["unrelated/_aiogram_nav_native.pyd"] = data.pop("_aiogram_nav_native.pyd")
    with zipfile.ZipFile(target, "w") as archive:
        for name, body in data.items():
            archive.writestr(name, body)
    with pytest.raises(ValueError, match="configured import path"):
        verify(project, native, dist, manifest(dist))


def test_maturin_wrapped_and_explicit_mixed_packages(tmp_path):
    _project, _native, dist = fixture(tmp_path)
    target = next(dist.glob("*win_amd64.whl"))
    with zipfile.ZipFile(target) as archive:
        data = {item: archive.read(item) for item in archive.namelist()}
    extension = data.pop("_aiogram_nav_native.pyd")
    for parent, full_name in (
        ("_aiogram_nav_native", "_aiogram_nav_native"),
        ("aiogram_nav_native", "aiogram_nav_native._aiogram_nav_native"),
    ):
        with zipfile.ZipFile(target, "w") as archive:
            for name, body in data.items():
                archive.writestr(name, body)
            archive.writestr(parent + "/__init__.py", b"# package wrapper")
            archive.writestr(parent + "/_aiogram_nav_native.pyd", extension)
        assert (
            module.wheel(target, "aiogram-nav-native", "0.3.0", module_name=full_name)
            == "windows-amd64"
        )
