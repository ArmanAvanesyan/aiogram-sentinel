# Changelog Entries

This directory contains changelog entries for the next release. Entries are organized by type in subdirectories.

## Directory Structure

```
CHANGES/
├── feature/        # New features (.rst files)
├── bugfix/         # Bug fixes (.rst files)
├── doc/            # Documentation changes (.rst files)
├── removal/        # Removed features (.rst files)
├── misc/           # Miscellaneous changes (.rst files)
└── README.md       # This file
```

## File Naming

Each file should be named like:

```
<issue or PR number>.<category>.rst
```

For example:
- `feature/1234.feature.rst` - New feature for issue #1234
- `bugfix/5678.bugfix.rst` - Bug fix for PR #5678
- `doc/9012.doc.rst` - Documentation update

## File Format

Each `.rst` file should contain a brief description:

```rst
Add support for Redis Cluster deployments.
```

## Examples

### Feature (`feature/123.feature.rst`)
```rst
Add token bucket rate limiting algorithm.
```

### Bug Fix (`bugfix/456.bugfix.rst`)
```rst
Fix memory leak in long-running processes.
```

### Documentation (`doc/789.doc.rst`)
```rst
Add comprehensive migration guides.
```

### Removal (`removal/101.removal.rst`)
```rst
Remove deprecated legacy authentication middleware.
```

### Miscellaneous (`misc/202.misc.rst`)
```rst
Update project dependencies.
```

## Notes

- Keep descriptions concise but informative
- Focus on user-facing changes
- Use present tense ("Add support" not "Added support")
- Reference issues/PRs in the filename, not the content
- One change per file
- Place files in the appropriate subdirectory by type
- Towncrier will process these automatically during releases