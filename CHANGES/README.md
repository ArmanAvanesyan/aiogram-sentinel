# Changelog Entries

This directory contains changelog entries for the next release. Each file should be named like:

```
<issue or PR number>.<category>.rst
```

For example:
- `1234.bugfix.rst` - Bug fix for issue #1234
- `5678.feature.rst` - New feature from PR #5678
- `9012.doc.rst` - Documentation update

## Categories

- **feature**: New features
- **bugfix**: Bug fixes
- **doc**: Documentation changes
- **removal**: Removed features
- **misc**: Miscellaneous changes

## File Format

Each file should contain a brief description of the changes:

```rst
Add support for Redis Cluster deployments.
```

## Examples

### Feature
```rst
Add token bucket rate limiting algorithm.
```

### Bug Fix
```rst
Fix memory leak in long-running processes.
```

### Documentation
```rst
Add comprehensive migration guides.
```

## Notes

- Keep descriptions concise but informative
- Focus on user-facing changes
- Use present tense ("Add support" not "Added support")
- Reference issues/PRs in the filename, not the content
- One change per file
- Files are placed directly in the CHANGES/ directory (no subdirectories)
