# Development Tools

This directory contains utility scripts for development and release management.

## Tools

### `check_version_tag.py`
**Purpose**: Validates that package versions match git tags during releases.

**Usage:**
```bash
uv run python tools/check_version_tag.py
```

**Requirements:**
- Must be run in CI environment with `GITHUB_REF` set
- Expects semver-compliant git tags (e.g., `v1.2.3`)
- Validates versions in:
  - `src/aiogram_sentinel/version.py` (`__version__`)
  - `pyproject.toml` (`project.version`)
  - Git tag (`GITHUB_REF`)

**Integration:** Automatically runs in release workflow on tag pushes.

### `gen_tree.py`
**Purpose**: Generates markdown-formatted directory structure.

**Usage:**
```bash
uv run python tools/gen_tree.py
```

**Output:** Creates clean directory tree for documentation that:
- Ignores build artifacts (`.git/`, `dist/`, `build/`)
- Ignores cache files (`__pycache__/`, `.pytest_cache/`)
- Ignores IDE files (`.cursor/`, `.DS_Store`)
- Sorts directories before files alphabetically

**Integration:** Manual use for documentation updates.

## Development Workflow

```bash
# Check versions before release
uv run python tools/check_version_tag.py

# Generate fresh directory tree for docs
uv run python tools/gen_tree.py > new_tree.md
```

## CI Integration

These tools are integrated into GitHub Actions:

- **Release workflow**: Runs version check on tag pushes
- **Documentation**: Directory tree can be generated as needed
- **Release validation**: Prevents version mismatches automatically
