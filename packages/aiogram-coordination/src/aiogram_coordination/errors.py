"""Public coordination and authority failures; no credentials in messages."""


class CoordinationError(Exception):
    """Base shared coordination failure."""


class ConfigurationError(CoordinationError, ValueError):
    """The requested setup cannot prove safe coordination."""


class OwnershipLost(CoordinationError):
    """The protected scope no longer owns its lock or lease."""


class PersistenceUnavailable(CoordinationError):
    """The lock's authoritative storage is unavailable."""


class SessionAuthorityUnavailable(CoordinationError):
    """Session lookup failed; this is not an unauthorized-session result."""
