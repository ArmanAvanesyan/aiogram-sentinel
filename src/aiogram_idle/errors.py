"""Typed failures. Exception messages never contain drafts or credentials."""


class IdleError(Exception):
    """Base class for public library failures."""


class ConfigurationError(IdleError, ValueError):
    """Configuration cannot support the requested behavior."""


class ConfigurationMismatch(ConfigurationError):
    """A runtime disagrees with the backend's established manifest."""


class UnsupportedContext(ConfigurationError):
    """A conversation cannot be represented safely."""


class ActivityConflict(IdleError):
    """The supplied activity generation is stale or already occupied."""


class VersionConflict(ActivityConflict):
    """A conditional mutation lost a race."""


class SessionExpired(IdleError):
    """A logical session is absent or no longer authorized."""


class OperationIdConflict(IdleError):
    """An operation ID has already been used for different caller intent."""


class OwnershipLost(IdleError):
    """The worker no longer owns its lease or operation."""


class Overloaded(IdleError):
    """Admission would evict unresolved recovery evidence."""


class PersistenceUnavailable(IdleError):
    """The authoritative backend is unavailable."""


class SessionAuthorityUnavailable(PersistenceUnavailable):
    """Application session lookup failed; no expiration may be inferred."""


class CommitUnknown(PersistenceUnavailable):
    """A backend mutation may have committed; lookup before retrying effects."""


class EffectUnknown(IdleError):
    """An external effect may have happened; blind replay is unsafe."""


class SchemaUnsupported(ConfigurationError):
    """The stored record or operation version is not supported."""


class BackendInconsistent(IdleError):
    """Stored state violates the backend's consistency contracts."""
