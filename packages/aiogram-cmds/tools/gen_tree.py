#!/usr/bin/env python3
"""
Directory tree generator for aiogram-cmds.

This script generates a markdown-formatted directory tree for documentation.
It automatically ignores build artifacts, cache files, and IDE files.

Usage:
    python tools/gen_tree.py [directory]

If no directory is specified, it uses the current directory.
"""

import sys
from pathlib import Path

# Patterns to ignore
IGNORE_PATTERNS: set[str] = {
    # Build artifacts
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".Python",
    "build",
    "develop-eggs",
    "dist",
    "downloads",
    "eggs",
    ".eggs",
    "lib",
    "lib64",
    "parts",
    "sdist",
    "var",
    "wheels",
    "*.egg-info",
    ".installed.cfg",
    "*.egg",
    "MANIFEST",
    # Virtual environments
    ".venv",
    "venv",
    "env",
    "ENV",
    "env.bak",
    "venv.bak",
    ".uv",
    # IDE files
    ".vscode",
    ".idea",
    "*.swp",
    "*.swo",
    "*~",
    # OS files
    ".DS_Store",
    ".DS_Store?",
    "._*",
    ".Spotlight-V100",
    ".Trashes",
    "ehthumbs.db",
    "Thumbs.db",
    "Thumbs.db:encryptable",
    "desktop.ini",
    # Git
    ".git",
    ".gitignore",
    ".gitattributes",
    # Documentation build
    "_build",
    "site",
    ".doctrees",
    # Testing
    ".pytest_cache",
    ".coverage",
    "htmlcov",
    ".tox",
    ".cache",
    "coverage.xml",
    "*.cover",
    ".hypothesis",
    # Logs
    "*.log",
    "logs",
    # Temporary files
    "*.tmp",
    "*.temp",
    "*.bak",
    "*.backup",
    "*.orig",
    # Project specific
    ".notes",
    "node_modules",
    ".npm",
    ".yarn",
    # Compiled files
    "*.mo",
    "*.pot",
    # Database files
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    # Redis
    "dump.rdb",
    # Jupyter
    ".ipynb_checkpoints",
    # MyPy
    ".mypy_cache",
    ".dmypy.json",
    "dmypy.json",
    # Pyre
    ".pyre",
    # Pytype
    ".pytype",
    # Cython
    "cython_debug",
}


def should_ignore(path: Path) -> bool:
    """Check if a path should be ignored."""
    # Check if any part of the path matches ignore patterns
    for part in path.parts:
        if part in IGNORE_PATTERNS:
            return True

        # Check for pattern matches
        for pattern in IGNORE_PATTERNS:
            if pattern.startswith("*") and part.endswith(pattern[1:]):
                return True
            elif pattern.endswith("*") and part.startswith(pattern[:-1]):
                return True
            elif "*" in pattern:
                # Simple glob matching
                import fnmatch

                if fnmatch.fnmatch(part, pattern):
                    return True

    return False


def generate_tree(directory: Path, prefix: str = "", is_last: bool = True) -> list[str]:
    """Generate directory tree structure."""
    lines = []

    if not directory.exists():
        return lines

    # Get directory name for display
    if directory.name == ".":
        display_name = directory.absolute().name
    else:
        display_name = directory.name

    # Add current directory
    if prefix:
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{display_name}/")
        new_prefix = prefix + ("    " if is_last else "│   ")
    else:
        lines.append(f"{display_name}/")
        new_prefix = ""

    # Get children (directories first, then files)
    try:
        children = sorted(
            directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        )
        children = [child for child in children if not should_ignore(child)]
    except PermissionError:
        return lines

    # Process children
    for i, child in enumerate(children):
        is_last_child = i == len(children) - 1

        if child.is_dir():
            # Recursively process directory
            sub_lines = generate_tree(child, new_prefix, is_last_child)
            lines.extend(sub_lines)
        else:
            # Add file
            connector = "└── " if is_last_child else "├── "
            lines.append(f"{new_prefix}{connector}{child.name}")

    return lines


def format_as_markdown(
    tree_lines: list[str], title: str = "Directory Structure"
) -> str:
    """Format tree lines as markdown code block."""
    lines = [f"# {title}", ""]
    lines.append("```")
    lines.extend(tree_lines)
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Main function."""
    # Parse command line arguments
    if len(sys.argv) > 1:
        directory = Path(sys.argv[1])
    else:
        directory = Path(".")

    if not directory.exists():
        print(f"❌ Directory does not exist: {directory}")
        return 1

    if not directory.is_dir():
        print(f"❌ Path is not a directory: {directory}")
        return 1

    try:
        # Generate tree
        print(f"🌳 Generating directory tree for: {directory.absolute()}")
        tree_lines = generate_tree(directory)

        if not tree_lines:
            print("❌ No files found (all files may be ignored)")
            return 1

        # Format as markdown
        title = f"Directory Structure: {directory.name}"
        markdown_output = format_as_markdown(tree_lines, title)

        # Output to stdout
        print(markdown_output)

        return 0

    except KeyboardInterrupt:
        print("\n⏹️  Generation interrupted by user")
        return 2

    except Exception as e:
        print(f"❌ Error generating tree: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
