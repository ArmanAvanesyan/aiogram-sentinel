"""Translate backend failures into the navigation repository's public taxonomy."""

from aiogram_nav import errors as navigation

from ... import errors as idle


def navigation_error(error: idle.IdleError) -> navigation.NavigationError:
    if isinstance(error, idle.OwnershipLost):
        return navigation.OwnershipLost("Integrated conversation ownership expired")
    if isinstance(error, idle.CommitUnknown):
        return navigation.CommitUnknown("Integrated navigation commit result is uncertain")
    if isinstance(error, idle.PersistenceUnavailable):
        return navigation.PersistenceUnavailable("Integrated navigation storage is unavailable")
    if isinstance(error, idle.SessionExpired):
        return navigation.SessionExpired("Integrated navigation authorization expired")
    if isinstance(error, idle.OperationIdConflict):
        return navigation.OperationIdConflict("Integrated operation ID has conflicting input")
    if isinstance(error, idle.ActivityConflict):
        return navigation.VersionConflict("Integrated activity or runtime guard changed")
    if isinstance(error, idle.Overloaded):
        return navigation.Overloaded("Integrated recovery evidence capacity exhausted")
    if isinstance(error, (idle.SchemaUnsupported, idle.BackendInconsistent)):
        return navigation.SchemaUnsupported("Integrated navigation persistence is inconsistent")
    return navigation.ConfigurationError("Integrated navigation configuration is unsupported")
