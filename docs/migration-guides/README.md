# Migration Guides

This directory contains migration guides for upgrading between different versions of aiogram-sentinel.

## Available Migration Guides

- **[v0.1.0 to v0.2.0](v0.1.0-to-v0.2.0.md)** - Hooks expansion and Redis prefix support
- **[v0.2.0 to v1.0.0](v0.2.0-to-v1.0.0.md)** - Token bucket implementation and stable API

## Migration Guide Template

When creating a new migration guide, use the following structure:

```markdown
# Migration Guide: vX.Y.Z to vA.B.C

## Overview

Brief description of what changed and why migration is needed.

## Breaking Changes

| Old API | New API | Impact | Migration Required |
|---------|---------|--------|-------------------|
| `old_method()` | `new_method()` | High | Yes |
| `deprecated_param` | `new_param` | Medium | Optional |

## Code Modifications

### Before (vX.Y.Z)

```python
# Old code example
```

### After (vA.B.C)

```python
# New code example
```

## Deprecations & Removal Timeline

- **vA.B.C**: Feature X deprecated
- **vA.B+1.C**: Feature X removed
- **vA.B+2.C**: Feature Y deprecated

## Automatic Migration Tools

If available, describe any tools or scripts that can help with migration.

## Need Help?

If you encounter issues during migration:
- Check the [Troubleshooting Guide](../troubleshooting.md)
- Open an issue on [GitHub](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)
- Join our [Discussions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)
```

## Version Compatibility

| aiogram-sentinel | Python | aiogram | Status |
|------------------|--------|---------|--------|
| v1.0.0+ | 3.10+ | 3.0+ | Current |
| v0.2.0 | 3.10+ | 3.0+ | Supported |
| v0.1.0 | 3.10+ | 3.0+ | Deprecated |

## Migration Support

- **Current Version**: Full support
- **Previous Major Version**: Security updates only
- **Older Versions**: Community support only

For questions about migration, please open an issue with the `migration` label.
