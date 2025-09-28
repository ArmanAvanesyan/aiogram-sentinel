# Contributing to aiogram-sentinel

Thank you for your interest in contributing to aiogram-sentinel! This document provides guidelines and instructions for contributing to the project.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Git

### Installation

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/your-username/aiogram-sentinel.git
   cd aiogram-sentinel
   ```

2. Install the package in development mode:
   ```bash
   # Using uv (recommended)
   uv sync --dev
   
   # Or using pip
   pip install -e .[dev]
   ```

3. Install pre-commit hooks (optional but recommended):
   ```bash
   pre-commit install
   ```

## Development Workflow

### Fast Development Loop

For quick iterations during development, use these commands:

```bash
# Code formatting and linting
uv run ruff check --fix .
uv run ruff format .

# Type checking
uv run pyright

# Run tests
uv run pytest

# Run specific test categories
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/perf/
```

### Code Quality Tools

The project uses several tools to maintain code quality:

#### Linting and Formatting
- **Ruff**: Fast Python linter and formatter
  ```bash
  uv run ruff check .          # Check for issues
  uv run ruff check --fix .    # Auto-fix issues
  uv run ruff format .         # Format code
  ```

#### Type Checking
- **Pyright**: Static type checker
  ```bash
  uv run pyright
  ```

#### Testing
- **pytest**: Test framework
  ```bash
  uv run pytest                    # Run all tests
  uv run pytest -v                 # Verbose output
  uv run pytest --tb=short         # Short traceback
  uv run pytest tests/unit/        # Run unit tests only
  ```

#### Security
- **Bandit**: Security linter
  ```bash
  uv run bandit -r src/
  ```

- **pip-audit**: Dependency vulnerability scanner
  ```bash
  uv run pip-audit
  ```

### Optional Deep Checks

For comprehensive code analysis (optional):

```bash
# Dead code detection
uv run vulture src/

# Code complexity analysis
uv run radon cc src/

# Maintainability index
uv run xenon --max-absolute B --max-modules A --max-average A src/
```

## Project Structure

```
aiogram-sentinel/
├── src/aiogram_sentinel/          # Main package
│   ├── middlewares/               # Middleware implementations
│   ├── routers/                   # Router implementations
│   ├── storage/                   # Storage backends
│   └── utils/                     # Utility functions
├── tests/                         # Test suite
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests
│   └── perf/                      # Performance tests
├── docs/                          # Documentation
├── examples/                      # Usage examples
├── tools/                         # Development tools
├── .github/                       # GitHub workflows and templates
└── .cursor/                       # Cursor IDE rules
```

## Coding Standards

### Code Style

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use type hints for all function parameters and return values
- Write docstrings for all public functions, classes, and modules
- Keep line length under 88 characters (Ruff default)

### Type Hints

Always use type hints:

```python
from typing import Any, Dict, List, Optional

def process_data(data: List[Dict[str, Any]]) -> Optional[str]:
    """Process the input data and return a result."""
    # Implementation here
    pass
```

### Documentation

- Use Google-style docstrings
- Include examples in docstrings when helpful
- Update documentation when adding new features

### Testing

- Write tests for all new functionality
- Aim for high test coverage
- Use descriptive test names
- Follow the AAA pattern (Arrange, Act, Assert)

## Commit Guidelines

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add Redis storage backend
fix: resolve memory leak in rate limiter
docs: update API documentation
test: add integration tests for middleware
```

### Commit Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes following the coding standards
3. Add tests for new functionality
4. Ensure all tests pass
5. Update documentation if needed
6. Submit a pull request using the provided template

### PR Checklist

Before submitting a PR, ensure:

- [ ] All tests pass
- [ ] Code is properly formatted (`ruff format`)
- [ ] No linting errors (`ruff check`)
- [ ] Type checking passes (`pyright`)
- [ ] Security checks pass (`bandit`)
- [ ] Documentation is updated
- [ ] Commit messages are clear

## Issue Reporting

When reporting issues:

1. Check existing issues to avoid duplicates
2. Use the provided issue template
3. Provide clear reproduction steps
4. Include environment details
5. Add relevant code examples

## Development Tools

### IDE Configuration

The project includes configuration for Cursor IDE in `.cursor/rules/`:

- **00-foundation.mcp**: Scope, public API, guardrails
- **01-architecture.mcp**: Layout & boundaries
- **02-style-python.mcp**: Code style & typing
- **03-style-aiogram.mcp**: aiogram v3 patterns
- **04-style-storage.mcp**: Storage & keying
- **05-style-docs.mcp**: Documentation requirements
- **06-style-ci.mcp**: CI & test conventions
- **07-style-security.mcp**: Security & privacy

### Pre-commit Hooks

If you've installed pre-commit hooks, they will automatically run:

- Code formatting (Ruff)
- Linting (Ruff)
- Type checking (Pyright)
- Security checks (Bandit)

## Release Process

Releases are automated via GitHub Actions:

1. Create a version tag: `git tag v0.1.0`
2. Push the tag: `git push origin v0.1.0`
3. The release workflow will automatically:
   - Build the package
   - Publish to PyPI
   - Create a GitHub release

## Getting Help

- Check the [documentation](docs/)
- Look at [examples](examples/)
- Review existing [issues](../../issues)
- Join discussions in [GitHub Discussions](../../discussions)

## Code of Conduct

Please be respectful and constructive in all interactions. We aim to create a welcoming environment for all contributors.

## License

By contributing to aiogram-sentinel, you agree that your contributions will be licensed under the MIT License.
