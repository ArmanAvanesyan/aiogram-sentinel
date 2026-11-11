"""Shared task-scoped coordination without Idle/Nav dependencies."""

from .errors import (
    ConfigurationError,
    CoordinationError,
    OwnershipLost,
    PersistenceUnavailable,
    SessionAuthorityUnavailable,
)
from .identity import CoordinationKey, coordination_key
from .isolation import AiogramMemoryCoordinator, TrackedEventIsolation
from .memory import MemoryCoordinator
from .protocols import (
    BorrowedFsmCoordinator,
    Coordinator,
    FencedCoordinator,
    IsolationProvider,
    LeaseHandle,
)
from .redis import RedisCoordinator
from .redis_isolation import RedisIsolationProvider, RenewableRedisEventIsolation
from .sessions import ExternalSession, SessionAuthority, validate_session_transition
from .version import __version__ as __version__

__all__ = [
    "BorrowedFsmCoordinator",
    "AiogramMemoryCoordinator",
    "TrackedEventIsolation",
    "RenewableRedisEventIsolation",
    "RedisIsolationProvider",
    "CoordinationKey",
    "coordination_key",
    "Coordinator",
    "FencedCoordinator",
    "MemoryCoordinator",
    "RedisCoordinator",
    "IsolationProvider",
    "LeaseHandle",
    "ExternalSession",
    "SessionAuthority",
    "validate_session_transition",
    "ConfigurationError",
    "CoordinationError",
    "OwnershipLost",
    "PersistenceUnavailable",
    "SessionAuthorityUnavailable",
]
