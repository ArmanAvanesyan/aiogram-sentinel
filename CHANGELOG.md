## [0.2.0] - 2026-11-10

### Features

- Separate description rendering from Telegram's language slot, add explicit
  obsolete-language cleanup, and support application-selected profiles with
  caller-owned payload confirmations and applied/unchanged/failed outcomes.
  Report partial batch application without claiming Telegram transactions.

### Bugfixes

- Manager failures now propagate unless best_effort=True, which returns False.
  Successful operations return True. Added generic application-selected
  update_profile.
  Corrected runtime version export, strict typing, plural i18n and scope
  validation. ([#9](https://github.com/ArmanAvanesyan/aiogram-cmds/issues/9))
- Use aiogram's locale context when translating command menus, so real gettext
  catalogs are applied instead of silently falling back to untranslated text.

### Documentation

- Clarify that the Redis extra installs a client only; no storage or
  coordination backend exists.
  Document failure migration and preserve flag-based APIs as compatibility
  interfaces. ([#9](https://github.com/ArmanAvanesyan/aiogram-cmds/issues/9))
- Document the shared repository responsibilities, canonical release process,
  private vulnerability reporting and reproducible contribution checks. Keep
  generated scan reports out of source control.

### Miscellaneous

- Fix changelog tooling: towncrier now sees fragments in ``CHANGES/``, the CI
  changelog check passes, and project contact addresses point to a working
  mailbox. ([#8](https://github.com/ArmanAvanesyan/aiogram-cmds/issues/8))


# Changelog

All notable changes to aiogram-cmds will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2024-01-XX

### Added
- Enhanced i18n integration with aiogram best practices
- Context-based locale switching in translator adapter using `I18n.with_locale()`
- Pluralization support for translations via `plural` and `count` parameters
- Babel workflow scripts for translation management (`tools/i18n/`)
- Comprehensive command registration guide with examples
- Unit tests for translator adapter with singular/plural and fallback behavior
- Documentation for I18n setup and middleware usage

### Changed
- Updated translator protocol to support optional pluralization while maintaining backward compatibility
- Improved middleware integration with `SimpleI18nMiddleware` instead of `FSMI18nMiddleware`
- Enhanced documentation and examples to show proper aiogram I18n integration
- Updated i18n tutorial to reflect best practices

### Fixed
- Locale resolution now uses aiogram's `with_locale` context instead of passing `locale` kwarg to `gettext`
- Better fallback handling for missing translations
- Improved error handling in translator adapter

## [Unreleased]

### Added
- Initial project structure and documentation
- Comprehensive test suite
- Development tools and utilities
- CI/CD pipeline configuration

### Changed
- Adopted aiogram-sentinel project structure and patterns
- Updated all configuration files for aiogram-cmds

### Fixed
- Package name references in configuration files
- URL references to point to aiogram-cmds repository

## [0.1.0] - 2024-01-XX

### Added
- **CommandScopeManager**: Central orchestrator for command management
- **Auto-setup**: Zero-configuration setup with `setup_commands_auto()`
- **Simple Mode**: Settings-based configuration with policies
- **Advanced Mode**: Full control with profiles, scopes, and custom resolvers
- **i18n Integration**: Built-in support for aiogram i18n with fallback handling
- **User Profiles**: Dynamic command sets based on user status
- **Multiple Scopes**: Support for all Telegram command scopes
- **Dynamic Updates**: Runtime command updates based on user actions
- **Type Safety**: Full type hints and strict type checking
- **Configuration Loading**: Support for pyproject.toml configuration
- **Profile Resolvers**: Custom logic for determining user profiles
- **Command Policies**: Flexible command selection based on user flags
- **Translation System**: Extensible translator protocol
- **Command Registry**: Profile-based command management
- **Builder System**: Efficient command building with validation
- **Settings Management**: Pydantic-based configuration models

### Features
- **Three Usage Modes**:
  - Auto-setup for quick start
  - Simple mode for basic customization
  - Advanced mode for full control
- **i18n Support**:
  - Multiple language support
  - Automatic fallback handling
  - Custom translation keys
- **User Profiles**:
  - Guest, user, premium, admin profiles
  - Dynamic profile switching
  - Profile-based access control
- **Command Scopes**:
  - All Telegram command scopes supported
  - Hierarchical scope management
  - Chat-specific and user-specific commands
- **Dynamic Updates**:
  - Real-time command updates
  - Event-driven command changes
  - User state management

### Documentation
- **Comprehensive Guides**:
  - Quickstart guide
  - Installation instructions
  - Configuration guide
  - Architecture overview
- **API Reference**:
  - Complete API documentation
  - Type hints and examples
  - Usage patterns
- **Tutorials**:
  - Basic setup tutorial
  - i18n integration tutorial
  - Advanced profiles tutorial
  - Dynamic commands tutorial
- **Examples**:
  - Basic bot example
  - i18n bot example
  - Profile-based bot example
  - Dynamic bot example

### Testing
- **Unit Tests**:
  - Command builder tests
  - Manager tests
  - Policy tests
  - Settings tests
- **Integration Tests**:
  - End-to-end workflows
  - Configuration loading
  - Profile resolution
- **Performance Tests**:
  - Command building benchmarks
  - Profile resolution benchmarks
  - Memory usage tests

### Development
- **CI/CD Pipeline**:
  - Automated testing
  - Code quality checks
  - Security scanning
  - Documentation deployment
- **Development Tools**:
  - Version consistency checker
  - Directory tree generator
  - Pre-commit hooks
- **Code Quality**:
  - Type checking with Pyright
  - Linting with Ruff
  - Formatting with Black
  - Security scanning with Bandit

## [0.1.1] - 2024-01-XX

### Added
- Initial package structure
- Basic command management functionality
- Simple configuration system
- Basic i18n support

### Changed
- Updated package metadata
- Improved error handling
- Enhanced logging

### Fixed
- Command validation issues
- Translation fallback handling
- Configuration loading errors

## [0.1.0] - 2024-01-XX

### Added
- Initial release
- Basic command management
- Simple configuration
- Documentation structure

---

## Release Notes Format

### Added
- New features and functionality

### Changed
- Changes in existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Now removed features

### Fixed
- Bug fixes

### Security
- Security improvements

## Version History

- **0.1.0**: Initial release with comprehensive command management
- **0.1.1**: Bug fixes and improvements
- **0.1.0**: Initial release

## Migration Guide

### Initial Release 0.1.0

The 0.1.0 release introduces comprehensive command management features:

#### New Features
- **Auto-setup**: Use `setup_commands_auto()` for zero-configuration setup
- **Advanced Configuration**: Use `CmdsConfig` for full control
- **Profile System**: Implement user profiles with `ProfileDef`
- **Dynamic Updates**: Use `update_user_commands()` for real-time updates

#### Breaking Changes
- Configuration structure has been enhanced (backward compatible)
- New optional parameters in some functions
- Enhanced type hints (may require code updates)

#### Migration Steps
1. Update to aiogram-cmds 0.1.0
2. Review new features and consider adopting auto-setup
3. Update type hints if using strict type checking
4. Test your existing configuration

### From aiogram built-in commands

If you're migrating from aiogram's built-in command management:

1. Install aiogram-cmds: `pip install aiogram-cmds`
2. Replace manual command setup with aiogram-cmds
3. Use auto-setup for quick migration
4. Gradually adopt advanced features as needed

## Support

For questions about releases and migrations:
- Check the [Documentation](https://aiogram-cmds.dev)
- Review [Migration Guides](https://aiogram-cmds.dev/migration/)
- Ask in [GitHub Discussions](https://github.com/ArmanAvanesyan/aiogram-cmds/discussions)
- Report issues in [GitHub Issues](https://github.com/ArmanAvanesyan/aiogram-cmds/issues)
