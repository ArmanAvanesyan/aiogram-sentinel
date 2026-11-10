"""Safe typed navigation failures; messages never include drafts or credentials."""


class NavigationError(Exception):
    """Base class for public failures."""


class ConfigurationError(NavigationError, ValueError):
    """Unsupported or inconsistent setup."""


class UnsupportedContext(ConfigurationError):
    """The actor/conversation scope cannot be represented safely."""


class NodeNotFound(NavigationError, LookupError):
    """The node is not present in the immutable registry."""


class InvalidParameters(NavigationError, ValueError):
    """Parameters do not satisfy the node contract."""


class AccessDenied(NavigationError):
    """The application did not authorize this action."""


class StaleView(NavigationError):
    """A control is no longer bound to the current authorized view."""


class VersionConflict(NavigationError):
    """Conditional state changed before commit."""


class SessionExpired(NavigationError):
    """The absolute logical session lifetime elapsed."""


class OperationIdConflict(NavigationError):
    """A stable operation ID was reused with different caller intent."""


class OperationPending(NavigationError):
    """An unresolved action owns the navigation slot."""


class OwnershipLost(NavigationError):
    """The action or coordination capability is no longer owned."""


class Overloaded(NavigationError):
    """Admission would evict retained recovery evidence."""


class PersistenceUnavailable(NavigationError):
    """The authoritative repository is unavailable."""


class CommitUnknown(PersistenceUnavailable):
    """A mutation may have committed; inspect its operation before retrying."""


class SchemaUnsupported(ConfigurationError):
    """A newer or unknown stored schema cannot be interpreted safely."""


class RenderUnknown(NavigationError):
    """A rendering effect may have happened; automatic replay is unsafe."""


class RenderFailed(NavigationError):
    """Rendering was definitely rejected or incomplete."""


PendingAction = OperationPending


class BackendInconsistent(PersistenceUnavailable):
    """Redis rejected an authoritative transaction or stored state is inconsistent."""
