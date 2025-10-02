# Reports Directory

This directory contains various automated reports generated during development and CI/CD processes.

## Structure

```
reports/
├── security/           # Security audit and vulnerability reports
├── coverage/           # Code coverage reports  
└── performance/        # Benchmark and performance test results
```

## Report Types

### Security Reports (`security/`)
- **Bandit**: Security issue detection and best practices
- **pip-audit**: Dependency vulnerability scanning
- **Bandit Report**: `bandit-report.json` (tracked in git for CI badges)
- **Pip Audit Report**: `pip-audit-report.json` (tracked in git for CI badges)

### Coverage Reports (`coverage/`)
- Generated during CI/CD to track test coverage
- HTML reports (`htmlcov/`) are ignored by git
- XML reports (`coverage.xml`) are ignored by git
- Coverage data (`.coverage`) is ignored by git

### Performance Reports (`performance/`)
- Benchmark results from `pytest-benchmark`
- Performance test data is cached in `.benchmarks/` (ignored by git)

## Git Tracking Policy

- **Security reports**: ✅ Tracked (needed for CI badges and monitoring)
- **Coverage reports**: 🚫 Ignored (generated dynamically in CI)
- **Performance reports**: 🚫 Ignored (cache files, generated on-demand)

This organization keeps the root directory clean while maintaining accessibility to important reports.
