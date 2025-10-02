# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2025-01-03

### Added
- Simplified middleware stack focusing on core rate limiting and debouncing
- Streamlined storage backends (memory and Redis)
- Comprehensive documentation structure with MkDocs
- GitHub Actions workflows for CI/CD, documentation, and release automation
- Towncrier for automated changelog generation
- PyPy compatibility testing across multiple operating systems
- Python 3.13 support to CI/CD pipeline
- Modern badge system with grouped layout
- Organized reports structure (security, coverage, performance)
- Professional README with dynamic badges

### Fixed
- Type checking errors with Pyright
- Linting issues with Ruff
- Performance test thresholds for CI stability
- CI workflow issues (uv commands, OIDC configuration)
- Security risk in pr-management.yml
- File organization and documentation links
- Missing badges and documentation gaps

### Changed
- Simplified middleware architecture for better maintainability
- Consolidated storage interfaces for Redis and memory backends
- Restructured documentation for clarity and accessibility
- Updated CI/CD strategy for trunk-based development
- Modernized badge presentation with progressive disclosure

### Removed
- AuthMiddleware and BlockingMiddleware (simplified API)
- ChatMember router (streamlined router structure)
- Redundant documentation files and duplicate content
- Semantic-release automation (moved to tag-driven releases)

## [0.1.0] - Initial Release

### Added
- Initial release of aiogram-sentinel
- Core rate limiting middleware for aiogram v3
- Memory and Redis storage backends
- Comprehensive test suite
- Basic documentation structure