# Release Process

This document outlines the release process for aiogram-sentinel, including versioning, automation, and publishing procedures.

## Versioning Scheme & Stability Policy

### Semantic Versioning

aiogram-sentinel follows [Semantic Versioning (SemVer)](https://semver.org/) with the format `MAJOR.MINOR.PATCH`:

- **MAJOR** (v2.0.0): Breaking changes, incompatible API changes
- **MINOR** (v1.1.0): New features, backward compatible
- **PATCH** (v1.0.1): Bug fixes, backward compatible

### Stability Policy

**v1.x.x (Stable API):**
- No breaking changes in v1.x.x releases
- New features added in minor releases
- Bug fixes in patch releases
- 12-month support for each major version

**v0.x.x (Pre-release):**
- Breaking changes allowed
- Rapid iteration and feedback
- No stability guarantees

### Version Lifecycle

| Version | Status | Support | End of Life |
|---------|--------|---------|-------------|
| v1.0.x | Current | Full | TBD |
| v0.2.x | Deprecated | Security only | v1.1.0 |
| v0.1.x | Deprecated | Security only | v1.0.0 |

## Release Checklist

### Pre-Release Checklist

- [ ] **Code Quality**
  - [ ] All tests passing (`pytest tests/`)
  - [ ] Linting clean (`ruff check .`)
  - [ ] Type checking clean (`pyright`)
  - [ ] Performance tests passing
  - [ ] Security scan clean

- [ ] **Documentation**
  - [ ] README.md updated
  - [ ] CHANGELOG.md updated
  - [ ] API documentation updated
  - [ ] Migration guides updated (if needed)
  - [ ] Examples tested and updated

- [ ] **Version Management**
  - [ ] Version bumped in `src/aiogram_sentinel/version.py`
  - [ ] Version bumped in `pyproject.toml`
  - [ ] Git tag created (`v1.0.0`)
  - [ ] Release notes prepared

- [ ] **Testing**
  - [ ] Unit tests: 100% coverage
  - [ ] Integration tests: Redis backend tested
  - [ ] Performance tests: No regressions
  - [ ] Manual testing: Key features verified

### Release Day Checklist

- [ ] **Final Verification**
  - [ ] CI/CD pipeline green
  - [ ] All quality gates passed
  - [ ] Security review completed
  - [ ] Performance benchmarks updated

- [ ] **Publishing**
  - [ ] PyPI package uploaded
  - [ ] GitHub release created
  - [ ] Release notes published
  - [ ] Announcement posted

- [ ] **Post-Release**
  - [ ] Monitor for issues
  - [ ] Update documentation links
  - [ ] Notify community
  - [ ] Update project status

## Automation

### GitHub Actions Workflow

The release process is automated using GitHub Actions:

```yaml
# .github/workflows/release.yml
name: Release to PyPI

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  release:
    name: Release
    runs-on: ubuntu-latest
    permissions:
      id-token: write # IMPORTANT: this permission is needed for trusted publishing

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"

      - name: Install build dependencies
        run: |
          uv add --dev hatchling
          uv tool install twine

      - name: Validate version against tag
        run: |
          python tools/check_version_tag.py

      - name: Build package
        run: |
          uv run python -m hatchling build

      - name: Check package
        run: |
          uv tool run --from twine twine check dist/*

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          skip-existing: true
```

### Automated Quality Gates

**Continuous Integration:**
- Code quality checks (linting, type checking)
- Test execution (unit, integration, performance)
- Security scanning
- Documentation validation

**Release Automation:**
- Version validation
- Package building
- PyPI publishing
- GitHub release creation

### Semantic Release (Future)

Planned integration with [semantic-release](https://github.com/semantic-release/semantic-release) for automated versioning:

```yaml
# .github/workflows/semantic-release.yml
name: Semantic Release

on:
  push:
    branches: [main]

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Semantic Release
        uses: cycjimmy/semantic-release-action@v4
        with:
          semantic_version: 19
          extra_plugins: |
            @semantic-release/changelog
            @semantic-release/git
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PYPI_TOKEN: ${{ secrets.PYPI_TOKEN }}
```

## Security Release Lane

### Security Vulnerability Process

**1. Vulnerability Discovery**
- Private reporting via [SECURITY.md](SECURITY.md)
- Security team assessment
- CVE assignment (if applicable)

**2. Security Release Preparation**
- Private development branch
- Security fix implementation
- Comprehensive testing
- Security review

**3. Coordinated Disclosure**
- Pre-release notification to major users
- Simultaneous release and disclosure
- Security advisory publication
- Community notification

### Security Release Checklist

- [ ] **Vulnerability Assessment**
  - [ ] Severity classification (Critical/High/Medium/Low)
  - [ ] Impact analysis
  - [ ] Affected versions identified
  - [ ] CVE requested (if applicable)

- [ ] **Fix Development**
  - [ ] Security fix implemented
  - [ ] Regression tests added
  - [ ] Security tests updated
  - [ ] Code review completed

- [ ] **Release Preparation**
  - [ ] Security advisory drafted
  - [ ] Release notes prepared
  - [ ] Migration guide updated
  - [ ] Community notification prepared

- [ ] **Release Execution**
  - [ ] Security release published
  - [ ] Advisory published
  - [ ] Community notified
  - [ ] Monitoring for issues

## Publishing

### PyPI Publishing

**Trusted Publishing (OIDC):**
- No API tokens required
- GitHub Actions integration
- Automatic package signing
- Secure publishing process

**Manual Publishing (Fallback):**
```bash
# Build package
python -m hatchling build

# Check package
twine check dist/*

# Upload to PyPI
twine upload dist/*
```

### Package Signing

**Automatic Signing:**
- GitHub Actions signs packages
- GPG key stored in GitHub Secrets
- Signed packages uploaded to PyPI

**Manual Signing:**
```bash
# Sign package
gpg --detach-sign --armor dist/aiogram_sentinel-1.0.0-py3-none-any.whl

# Upload signed package
twine upload --sign dist/*
```

### GitHub Releases

**Automatic Release Creation:**
- GitHub Actions creates releases
- Release notes from CHANGELOG.md
- Assets attached (source, wheels)
- Pre-release flag for beta versions

**Manual Release Creation:**
```bash
# Create release
gh release create v1.0.0 \
  --title "aiogram-sentinel v1.0.0" \
  --notes-file CHANGELOG.md \
  --attach dist/aiogram_sentinel-1.0.0.tar.gz \
  --attach dist/aiogram_sentinel-1.0.0-py3-none-any.whl
```

## Release Notes

### CHANGELOG.md Format

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New features for next release

### Changed
- Changes in existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security improvements

## [1.0.0] - 2024-03-15

### Added
- Initial stable release
- Core middleware functionality
- Memory and Redis backends
- Comprehensive documentation

### Changed
- Stable API commitment
- Performance optimizations

### Fixed
- Various bug fixes and improvements
```

### Release Notes Template

```markdown
# aiogram-sentinel v1.0.0

## 🎉 What's New

### Major Features
- **Stable API**: No breaking changes in v1.x.x releases
- **Token Bucket**: Improved rate limiting algorithm
- **Performance**: 50% faster middleware execution

### New Features
- Redis Cluster support
- Advanced rate limiting options
- Performance monitoring hooks

## 🔧 Changes

### Added
- `@sentinel_rate_limit` decorator with token bucket support
- Redis Cluster backend
- Performance monitoring hooks
- Migration guides

### Changed
- Rate limiting algorithm improved
- Memory usage optimized
- Documentation expanded

### Fixed
- Memory leak in long-running processes
- Redis connection handling
- Type annotation issues

## 🚀 Migration Guide

See [Migration Guide](docs/migration-guides/v0.2.0-to-v1.0.0.md) for detailed upgrade instructions.

## 📦 Installation

```bash
pip install aiogram-sentinel==1.0.0
```

## 🔗 Links

- [Documentation](https://aiogram-sentinel.readthedocs.io/)
- [GitHub Repository](https://github.com/ArmanAvanesyan/aiogram-sentinel)
- [PyPI Package](https://pypi.org/project/aiogram-sentinel/)
```

## Monitoring & Rollback

### Post-Release Monitoring

**Metrics to Monitor:**
- Download statistics
- Error rates
- Performance metrics
- Community feedback

**Monitoring Tools:**
- PyPI download stats
- GitHub issue tracker
- Performance monitoring
- User feedback channels

### Rollback Procedure

**Emergency Rollback:**
1. Identify critical issues
2. Assess impact and severity
3. Decide on rollback strategy
4. Execute rollback plan
5. Communicate with community

**Rollback Options:**
- **Package Rollback**: Remove problematic version from PyPI
- **Hotfix Release**: Quick patch release
- **Communication**: Inform users of issues and workarounds

## Release Calendar

### 2024 Release Schedule

| Version | Target Date | Status | Focus |
|---------|-------------|--------|-------|
| v1.0.0 | March 2024 | ✅ Released | Stable API |
| v1.1.0 | June 2024 | 🔄 Planning | Performance |
| v1.2.0 | September 2024 | 📋 Planned | Advanced Features |
| v1.3.0 | December 2024 | 📋 Planned | Enterprise |

### Release Planning

**Quarterly Planning:**
- Q1: Feature planning and development
- Q2: Testing and quality assurance
- Q3: Release preparation and execution
- Q4: Post-release monitoring and feedback

**Release Criteria:**
- All quality gates passed
- Community feedback incorporated
- Performance benchmarks met
- Security review completed

## Contact & Support

### Release Team

- **Release Manager**: [@ArmanAvanesyan](https://github.com/ArmanAvanesyan)
- **Security Team**: [security@aiogram-sentinel.dev](mailto:security@aiogram-sentinel.dev)
- **Community**: [GitHub Discussions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)

### Emergency Contacts

- **Critical Issues**: [@ArmanAvanesyan](https://github.com/ArmanAvanesyan)
- **Security Issues**: [security@aiogram-sentinel.dev](mailto:security@aiogram-sentinel.dev)
- **Community Issues**: [GitHub Discussions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)

---

**Last Updated**: March 2024
**Next Review**: June 2024
