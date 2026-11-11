"""Standalone navigation for aiogram 3; no idle or Redis dependency."""

from aiogram_coordination import ExternalSession, SessionAuthority, TrackedEventIsolation

from .bindings_router import create_bindings_router
from .clock import Clock, ManualClock, SystemClock
from .config import NavigationConfig
from .context import NavigationContext
from .engine import EngineName
from .errors import (
    AccessDenied,
    BackendInconsistent,
    CommitUnknown,
    ConfigurationError,
    InvalidParameters,
    NavigationError,
    NodeNotFound,
    OperationIdConflict,
    OperationPending,
    Overloaded,
    OwnershipLost,
    PendingAction,
    PersistenceUnavailable,
    RenderFailed,
    RenderUnknown,
    SchemaUnsupported,
    SessionExpired,
    StaleView,
    UnsupportedContext,
    VersionConflict,
)
from .identity import IdentityResolver, private_identity
from .inputs import CallbackEntry, CommandEntry, InputBindings, ReplyEntry, prepare_token
from .isolation import AiogramMemoryCoordinator, MemoryCoordinator
from .json import JsonObject, JsonValue, timestamp_ms
from .models import (
    ActionStatus,
    CommitResult,
    ConversationKey,
    EffectCheckpoint,
    HistoryEntry,
    MessageRef,
    NavigationAction,
    NavigationEvent,
    NavigationIntent,
    NavigationMutation,
    NavigationSnapshot,
    NavigationToken,
    Node,
    PreparedAction,
    RenderRequest,
    RenderResult,
    VersionedSnapshot,
    ViewState,
)
from .navigation import Navigation
from .protocols import Coordinator, EffectRecorder
from .registry import NavigationRegistry
from .rejections import CallbackRejection, CallbackRejectionResponder
from .rendering.application import ApplicationPresenter
from .rendering.base import CleanupRequest, CleanupResult, NavigationPresenter, ScreenSpec
from .rendering.text import TextPresenter
from .storage.base import AtomicAdoptionRepository, NavigationRepository
from .storage.deployment import RedisDeploymentAttestation
from .storage.ledger import LedgerDelta, LedgerRead
from .storage.ledger_reducer import NavigationLedgerReducer
from .storage.memory import MemoryNavigationRepository
from .storage.sessions import StorageMigrationReport
from .version import __version__ as __version__

__all__ = [
    "EngineName",
    "AtomicAdoptionRepository",
    "LedgerRead",
    "LedgerDelta",
    "NavigationLedgerReducer",
    "create_bindings_router",
    "CallbackRejection",
    "CallbackRejectionResponder",
    "ExternalSession",
    "SessionAuthority",
    "RedisDeploymentAttestation",
    "StorageMigrationReport",
    "TrackedEventIsolation",
    "ApplicationPresenter",
    "AccessDenied",
    "BackendInconsistent",
    "ActionStatus",
    "AiogramMemoryCoordinator",
    "CallbackEntry",
    "CleanupRequest",
    "CleanupResult",
    "Clock",
    "CommandEntry",
    "CommitResult",
    "CommitUnknown",
    "ConfigurationError",
    "ConversationKey",
    "Coordinator",
    "EffectCheckpoint",
    "EffectRecorder",
    "HistoryEntry",
    "IdentityResolver",
    "InputBindings",
    "InvalidParameters",
    "JsonObject",
    "JsonValue",
    "ManualClock",
    "MemoryCoordinator",
    "MemoryNavigationRepository",
    "MessageRef",
    "Navigation",
    "NavigationAction",
    "NavigationConfig",
    "NavigationContext",
    "NavigationError",
    "NavigationEvent",
    "NavigationIntent",
    "NavigationMutation",
    "NavigationPresenter",
    "NavigationRegistry",
    "NavigationRepository",
    "NavigationSnapshot",
    "NavigationToken",
    "Node",
    "NodeNotFound",
    "OperationIdConflict",
    "OperationPending",
    "Overloaded",
    "OwnershipLost",
    "PendingAction",
    "PersistenceUnavailable",
    "PreparedAction",
    "RenderFailed",
    "RenderRequest",
    "RenderResult",
    "RenderUnknown",
    "ReplyEntry",
    "SchemaUnsupported",
    "ScreenSpec",
    "SessionExpired",
    "StaleView",
    "SystemClock",
    "TextPresenter",
    "UnsupportedContext",
    "VersionConflict",
    "VersionedSnapshot",
    "ViewState",
    "prepare_token",
    "private_identity",
    "timestamp_ms",
]
