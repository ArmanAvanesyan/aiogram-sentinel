param(
    [string]$Version = "0.1.1",
    [string]$Branch = "main"
)

Write-Host "🚀 Starting deployment for version $Version" -ForegroundColor Green

# Check if we're on the right branch
$currentBranch = git branch --show-current
if ($currentBranch -ne $Branch) {
    Write-Host "❌ Not on $Branch branch. Current: $currentBranch" -ForegroundColor Red
    exit 1
}

# Check if working directory is clean
$status = git status --porcelain
if ($status) {
    Write-Host "❌ Working directory is not clean. Please commit or stash changes." -ForegroundColor Red
    exit 1
}

# Verify version consistency
Write-Host "🔍 Checking version consistency..." -ForegroundColor Yellow
python tools/check_version_tag.py

# Run tests
Write-Host "🧪 Running tests..." -ForegroundColor Yellow
uv run pytest tests/ -v

# Create and push tag
Write-Host "🏷️  Creating tag v$Version..." -ForegroundColor Yellow
git tag "v$Version"
git push origin "v$Version"

Write-Host "✅ Deployment initiated! Check GitHub Actions for progress." -ForegroundColor Green
Write-Host "📦 PyPI: https://pypi.org/project/aiogram-cmds/" -ForegroundColor Cyan
Write-Host "🏷️  GitHub: https://github.com/ArmanAvanesyan/aiogram-cmds/releases" -ForegroundColor Cyan
