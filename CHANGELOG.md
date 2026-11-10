# Changelog

<!-- towncrier release notes start -->

## [1.2.0] - 2026-11-10

### Added

- Opt-in message, command and callback-query policies and action-kind buckets.
- Explicit command/callback-prefix spam exemptions without bypassing application guards.
- Configurable exception passthrough for infrastructure failures and webhook HTTP 503 handling.
- Startup warning for empty protected router subtrees, application-owned Redis guidance,
  migration documentation and a runnable protected-router example.

### Fixed

- Resolve named and legacy handler policies from the registered aiogram callback.
- Preserve application/error middleware when replacing rate-limit hooks and validate installation ownership.
- Make Redis optional at import/install time and commit rate-counter expiry atomically.
- Keep Sentry availability guards active under optimized Python and validate backend intervals.
- Correct project metadata/runtime version checks, ship py.typed, and maintain strict typing.
- Correct published repository links and verify minimum/current artifacts and real Redis in CI.

### Release process

- Publish exact reviewed distributions through the manual tag-bound release workflow.
- Keep generated security evidence in CI artifacts and update patched dependency locks.

## [1.1.0] - 2025-10-14

Published baseline containing the policy registry, scope/key-builder APIs and error middleware.
Version 1.2.0 corrects policy propagation and integration behavior; these baseline APIs are not new in 1.2.0.

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