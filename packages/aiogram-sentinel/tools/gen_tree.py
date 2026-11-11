#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

IGNORE = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".coverage",
    "htmlcov",
    ".DS_Store",
    "__pycache__",
    ".specstory",
    ".cursor",
    ".cache",
    "assets",
    "tmp",
}

ROOT = Path(".").resolve()


def is_ignored(p: Path) -> bool:
    parts = set(p.parts)
    return bool(parts & IGNORE)


def tree(dir: Path, prefix: str = "") -> list[str]:
    entries = [
        e
        for e in sorted(dir.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        if not is_ignored(e)
    ]
    lines: list[str] = []
    for i, e in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        lines.append(prefix + connector + e.name)
        if e.is_dir():
            extension = "    " if i == len(entries) - 1 else "│   "
            lines.extend(tree(e, prefix + extension))
    return lines


def main():
    print("# Directory Structure (generated)\n")
    print(f"_Root: {ROOT.name}_\n")
    print("```\n" + ROOT.name)
    for line in tree(ROOT):
        print(line)
    print("```")


if __name__ == "__main__":
    main()
