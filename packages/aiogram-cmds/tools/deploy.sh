#!/bin/bash
set -e

VERSION="0.1.1"
BRANCH="main"

echo "🚀 Starting deployment for version $VERSION"

# Check if we're on the right branch
current_branch=$(git branch --show-current)
if [ "$current_branch" != "$BRANCH" ]; then
    echo "❌ Not on $BRANCH branch. Current: $current_branch"
    exit 1
fi

# Check if working directory is clean
if ! git diff-index --quiet HEAD --; then
    echo "❌ Working directory is not clean. Please commit or stash changes."
    exit 1
fi

# Verify version consistency
echo "🔍 Checking version consistency..."
python tools/check_version_tag.py

# Run tests
echo "🧪 Running tests..."
uv run pytest tests/ -v

# Create and push tag
echo "🏷️  Creating tag v$VERSION..."
git tag v$VERSION
git push origin v$VERSION

echo "✅ Deployment initiated! Check GitHub Actions for progress."
echo "📦 PyPI: https://pypi.org/project/aiogram-cmds/"
echo "🏷️  GitHub: https://github.com/ArmanAvanesyan/aiogram-cmds/releases"
