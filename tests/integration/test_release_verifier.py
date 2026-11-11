"""Publishing rejects tampering before any upload is authorized."""

import hashlib
import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "tools/verify_release.py"
spec = importlib.util.spec_from_file_location("verify_release", SOURCE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def release(tmp_path):
    package = "aiogram-nav"
    project = tmp_path / "packages" / package
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text('[project]\nname="aiogram-nav"\nversion="0.3.1"\n')
    dist = tmp_path / "dist"
    dist.mkdir()
    metadata = b"Metadata-Version: 2.4\nName: aiogram-nav\nVersion: 0.3.1\n"
    with zipfile.ZipFile(dist / "aiogram_nav-0.3.1-py3-none-any.whl", "w") as archive:
        archive.writestr("aiogram_nav-0.3.1.dist-info/METADATA", metadata)
    with tarfile.open(dist / "aiogram_nav-0.3.1.tar.gz", "w:gz") as archive:
        member = tarfile.TarInfo("aiogram_nav-0.3.1/PKG-INFO")
        member.size = len(metadata)
        archive.addfile(member, io.BytesIO(metadata))
    manifest = dist / "SHA256SUMS"
    manifest.write_text(
        "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
            for p in sorted(dist.iterdir())
        )
    )
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return tmp_path, package, "aiogram-nav-v0.3.1", dist, digest


def test_accepts_reviewed_artifacts(release):
    module.verify(*release)


@pytest.mark.parametrize(
    "index,value",
    [
        (1, "unknown"),
        (2, "v0.3.1"),
        (2, "aiogram-idle-v0.3.1"),
        (2, "aiogram-nav-v0.3.2"),
        (4, "0" * 64),
        (4, "../unsafe"),
    ],
)
def test_rejects_invalid_identity(release, index, value):
    args = list(release)
    args[index] = value
    with pytest.raises(ValueError):
        module.verify(*args)


@pytest.mark.parametrize("change", ["extra", "tamper", "missing", "duplicate", "wrong-metadata"])
def test_rejects_changed_artifacts(release, change):
    root, package, tag, dist, digest = release
    manifest = dist / "SHA256SUMS"
    wheel = dist / "aiogram_nav-0.3.1-py3-none-any.whl"
    if change == "extra":
        (dist / "unexpected.whl").write_bytes(b"bad")
    elif change == "tamper":
        wheel.write_bytes(b"bad")
    elif change == "missing":
        wheel.unlink()
    elif change == "duplicate":
        manifest.write_text(manifest.read_text() + manifest.read_text().splitlines()[0] + "\n")
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    else:
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                "aiogram_nav-0.3.1.dist-info/METADATA", "Name: other\nVersion: 0.3.1\n"
            )
        manifest.write_text(
            "".join(
                f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
                for p in sorted(dist.iterdir())
                if p.name != "SHA256SUMS"
            )
        )
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        module.verify(root, package, tag, dist, digest)
