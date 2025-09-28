## [0.2.0] - 2024-12-28

### Features

- Add comprehensive documentation structure with MkDocs.
  ([#1](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/1))
- Add GitHub Actions workflows for CI/CD, documentation, and release
  automation.
  ([#2](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/2))
- Add Towncrier for automated changelog generation and PR enforcement.
  ([#3](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/3))
- Add PyPy compatibility testing across multiple operating systems.
  ([#4](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/4))
- Add Python 3.13 support to CI/CD pipeline and project configuration.
  ([#5](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/5))

### Bugfixes

- Fix type checking errors with Pyright and resolve linting issues with Ruff.
  ([#6](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/6))
- Fix test failures in unit and integration tests, including Redis connection
  issues. ([#7](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/7))
- Fix performance test assertions and middleware configuration parsing.
  ([#8](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/8))

### Documentation

- Add comprehensive API documentation, tutorials, and migration guides.
  ([#9](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/9))
- Add architecture documentation with sequence diagrams and performance
  benchmarks.
  ([#10](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/10))

### Miscellaneous

- Optimize GitHub Actions workflows by consolidating PR management and
  standardizing versions.
  ([#11](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/11))
- Add security policy, code of conduct, and issue templates for better project
  governance.
  ([#12](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues/12))


# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive documentation structure
- Quickstart guide for new users
- Tutorials for common use cases
- API reference documentation
- Configuration guide
- Troubleshooting guide
- FAQ section
- Security policy
- Code of conduct
- Issue templates for different types of reports
- Pull request template
- CODEOWNERS file
- Dependabot configuration
- Release workflow with PyPI publishing
- Version validation script

### Changed
- Improved error handling in middleware
- Enhanced type annotations throughout the codebase
- Better configuration validation
- More robust Redis connection handling

### Fixed
- Fixed type checking errors with Pyright
- Resolved linting issues with Ruff
- Fixed test failures in unit and integration tests
- Corrected performance test assertions
- Fixed middleware configuration parsing
- Resolved Redis integration test issues

### Security
- Added comprehensive security policy
- Implemented secure Redis connection guidelines
- Added input validation recommendations
- Enhanced error handling to prevent information disclosure

## [0.1.0] - 2024-09-28

### Added
- Initial release of aiogram-sentinel
- Core middleware system with four protection layers:
  - **ThrottlingMiddleware**: Rate limiting with configurable windows
  - **DebouncingMiddleware**: Duplicate message prevention
  - **AuthMiddleware**: User registration and context management
  - **BlockingMiddleware**: User blocking with configurable blocklists
- Storage backends:
  - **MemoryStorage**: Fast in-memory storage for development
  - **RedisStorage**: Persistent Redis-based storage for production
- Configuration system with `SentinelConfig` class
- Decorator support for handler-specific configuration:
  - `@sentinel_rate_limit`: Custom rate limiting per handler
  - `@sentinel_debounce`: Custom debouncing per handler
  - `@sentinel_require_registered`: Require user registration
- Utility functions for key generation and fingerprinting
- Comprehensive test suite with unit, integration, and performance tests
- Type hints throughout the codebase
- Exception handling with custom exception types
- Hooks for custom event handling (rate limit exceeded, etc.)
- Support for both polling and webhook modes
- Cross-platform compatibility (Windows, macOS, Linux)
- Python 3.10+ support

### Features
- **Rate Limiting**: Configurable message rate limits with sliding window
- **Debouncing**: Prevent duplicate message processing within time windows
- **User Blocking**: Block/unblock users with persistent storage
- **Authentication**: Automatic user registration and context management
- **Storage Flexibility**: Choose between memory and Redis backends
- **Handler-Specific Config**: Different protection levels per handler
- **Event Hooks**: Custom callbacks for rate limit events
- **Type Safety**: Full type annotations and type checking support
- **Performance**: Optimized for high-throughput scenarios
- **Extensibility**: Easy to extend with custom middleware and storage

### Technical Details
- Built on aiogram v3 middleware system
- Async/await support throughout
- Protocol-based architecture for easy extension
- Comprehensive error handling and logging
- Memory-efficient data structures
- Redis connection pooling and health checks
- Automatic cleanup of expired entries
- Thread-safe operations where applicable

### Dependencies
- aiogram >= 3.0.0
- redis >= 4.0.0 (optional, for Redis storage)
- Python >= 3.10

### Documentation
- README with quick start guide
- Architecture documentation
- Hooks documentation
- Testing guidelines
- Security guidelines
- Roadmap for future development

### Examples
- Minimal bot example
- Configuration examples
- Storage backend examples
- Custom middleware examples

## [0.0.1] - 2024-09-01

### Added
- Initial project setup
- Basic project structure
- Core middleware prototypes
- Initial test framework
- Basic documentation structure

---

## Release Notes

### Version 0.1.0

This is the first stable release of aiogram-sentinel, providing a comprehensive protection system for aiogram v3 bots. The library includes four core middleware components that work together to provide robust protection against spam, abuse, and unwanted behavior.

#### Key Features

1. **Rate Limiting**: Prevent users from sending too many messages within a time window
2. **Debouncing**: Avoid processing duplicate messages within a short time period
3. **User Blocking**: Block and unblock users with persistent storage
4. **Authentication**: Automatically register users and manage their context

#### Storage Options

- **Memory Storage**: Fast, in-memory storage perfect for development and testing
- **Redis Storage**: Persistent, scalable storage for production environments

#### Configuration

The library provides flexible configuration options:
- Global defaults for all protection features
- Handler-specific overrides using decorators
- Environment variable support
- Configuration file support

#### Getting Started

```python
from aiogram import Bot, Dispatcher
from aiogram_sentinel import Sentinel

bot = Bot(token="YOUR_TOKEN")
dp = Dispatcher()

sentinel = Sentinel()
dp.message.middleware(sentinel.middleware)

@dp.message()
async def handle_message(message):
    await message.answer("Hello!")
```

#### Migration from Other Libraries

If you're migrating from other protection libraries, aiogram-sentinel provides a clean, modern API that's easy to integrate into existing aiogram v3 bots.

#### Performance

The library is designed for high-performance scenarios:
- Memory-efficient data structures
- Optimized Redis operations
- Minimal overhead on message processing
- Automatic cleanup of expired data

#### Security

Security is a top priority:
- No sensitive data logging
- Secure Redis connection support
- Input validation and sanitization
- Comprehensive error handling

#### Community

We welcome contributions from the community:
- Bug reports and feature requests
- Code contributions
- Documentation improvements
- Testing and feedback

#### Support

- GitHub Issues for bug reports and feature requests
- GitHub Discussions for questions and community support
- Comprehensive documentation and examples
- Active maintenance and updates

---

## Contributing

We welcome contributions to aiogram-sentinel! Please see our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute.

### Reporting Issues

If you find a bug or have a feature request, please open an issue on GitHub using the appropriate template.

### Pull Requests

When submitting a pull request, please:
1. Follow the existing code style
2. Add tests for new functionality
3. Update documentation as needed
4. Ensure all tests pass
5. Follow the conventional commit format

### Development

To set up a development environment:

```bash
git clone https://github.com/ArmanAvanesyan/aiogram-sentinel.git
cd aiogram-sentinel
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

### Testing

Run the test suite:

```bash
# Unit tests
uv run pytest tests/unit/

# Integration tests (requires Redis)
export TEST_REDIS_URL=redis://localhost:6379/1
uv run pytest tests/integration/

# Performance tests
uv run pytest tests/perf/
```

### Code Quality

We use several tools to maintain code quality:

```bash
# Linting and formatting
uv run ruff check --fix .
uv run ruff format .

# Type checking
uv run pyright

# Security checks
uv run bandit -r src
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Thanks to the aiogram team for the excellent framework
- Thanks to all contributors who have helped improve this project
- Thanks to the Python community for the amazing ecosystem
- Thanks to Redis for the powerful data storage solution

---

## Links

- [GitHub Repository](https://github.com/ArmanAvanesyan/aiogram-sentinel)
- [PyPI Package](https://pypi.org/project/aiogram-sentinel/)
- [Documentation](https://github.com/ArmanAvanesyan/aiogram-sentinel/tree/main/docs)
- [Issue Tracker](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)
- [Discussions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)
