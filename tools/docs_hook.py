"""Expose package-owned documentation in one site without copying its sources."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://github.com/ArmanAvanesyan/aiogram-kit/blob/main/"
PACKAGES = [
    "aiogram-coordination",
    "aiogram-sentinel",
    "aiogram-cmds",
    "aiogram-nav",
    "aiogram-idle",
]


def on_files(files, config):
    for package in PACKAGES:
        directory = ROOT / "packages" / package
        sources = [directory / "README.md", *(directory / "docs").rglob("*")]
        for source in sources:
            if not source.is_file():
                continue
            relative = source.relative_to(directory)
            uri = f"libraries/{package}/{relative.as_posix()}"
            if source.suffix.lower() != ".md":
                files.append(File.generated(config, uri, abs_src_path=str(source)))
                continue
            text = source.read_text()

            def link(match, source=source, directory=directory):
                target = match.group(2)
                if not target or urlsplit(target).scheme or target.startswith(("#", "/")):
                    return match.group(0)
                # Keep internal document and image links local. Route links to source,
                # examples and other repository files to their canonical GitHub path.
                path = (source.parent / target.split("#", 1)[0]).resolve()
                if path.is_relative_to(directory / "docs") or path == directory / "README.md":
                    return match.group(0)
                if path.is_relative_to(directory):
                    suffix = "#" + target.split("#", 1)[1] if "#" in target else ""
                    return f"{match.group(1)}{BASE}{path.relative_to(ROOT).as_posix()}{suffix}{match.group(3)}"
                return match.group(0)

            text = re.sub(r"(\]\()([^\s)]+)(\))", link, text)
            files.append(File.generated(config, uri, content=text))
    return files
