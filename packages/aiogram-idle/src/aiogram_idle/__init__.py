"""Standalone inactivity policies for aiogram 3; no navigation or Redis dependency."""

from importlib.metadata import PackageNotFoundError, version

from .activity import IdleContext
from .clock import Clock, ManualClock, SystemClock
from .config import AmbiguousSendPolicy, IdleConfig
from .controls import (
    CommandPromptControls,
    ControlContext,
    ControlResult,
    InlinePromptControls,
    ReplyPromptControls,
)
from .coordinator import AiogramMemoryCoordinator, MemoryCoordinator
from .errors import (
    ActivityConflict,
    BackendInconsistent,
    CommitUnknown,
    ConfigurationError,
    ConfigurationMismatch,
    EffectUnknown,
    IdleError,
    OperationIdConflict,
    Overloaded,
    OwnershipLost,
    PersistenceUnavailable,
    SchemaUnsupported,
    SessionAuthorityUnavailable,
    SessionExpired,
    UnsupportedContext,
    VersionConflict,
)
from .events import IdleOutcome, coarse_event_sink
from .models import (
    ActionReceipt,
    ActivityGuard,
    ActivitySnapshot,
    ActivitySpec,
    ConfigManifest,
    ConfigUpdate,
    FlowContext,
    FlowEligibility,
    IdleConversationKey,
    IdleEvent,
    IdleSnapshot,
    IdleStatus,
    MessageRef,
    PendingOperation,
    Phase,
    PollReport,
    ReconcileReport,
    RuntimeSnapshot,
    SessionGuard,
    SessionSnapshot,
)
from .policies import ExemptPolicy, IdlePolicies, PromptPolicy, QuietRestorePolicy
from .presentation import (
    DeliveryReceipt,
    FinishRequest,
    PromptReceipt,
    PromptRequest,
    PromptTexts,
    QuietHours,
    QuietHoursResolver,
    TelegramPromptPresenter,
)
from .protocols import Coordinator, EffectRecorder, FlowAdapter, PromptPresenter, SessionAuthority
from .registration import ActivityRegistration
from .runtime import IdleRuntime
from .storage.activation import StorageMigrationPage
from .storage.base import IdleBackend
from .storage.deployment import RedisDeploymentAttestation
from .storage.format import StorageActivation
from .storage.memory import MemoryIdleBackend
from .storage.state import OperationLookup

try:
    __version__ = version("aiogram-idle")
except PackageNotFoundError:  # Allow direct source imports before installation.
    __version__ = "0+unknown"
__all__ = [
    "ActionReceipt",
    "ActivityConflict",
    "ActivityRegistration",
    "ActivityGuard",
    "ActivitySnapshot",
    "ActivitySpec",
    "AiogramMemoryCoordinator",
    "AmbiguousSendPolicy",
    "BackendInconsistent",
    "Clock",
    "CommandPromptControls",
    "CommitUnknown",
    "ConfigManifest",
    "ConfigUpdate",
    "ConfigurationError",
    "ConfigurationMismatch",
    "ControlContext",
    "ControlResult",
    "Coordinator",
    "DeliveryReceipt",
    "EffectRecorder",
    "EffectUnknown",
    "ExemptPolicy",
    "FinishRequest",
    "FlowAdapter",
    "FlowContext",
    "FlowEligibility",
    "IdleBackend",
    "IdleConfig",
    "IdleContext",
    "IdleConversationKey",
    "IdleError",
    "IdleEvent",
    "IdleOutcome",
    "IdlePolicies",
    "IdleRuntime",
    "IdleSnapshot",
    "IdleStatus",
    "InlinePromptControls",
    "ManualClock",
    "MemoryCoordinator",
    "MemoryIdleBackend",
    "MessageRef",
    "OperationIdConflict",
    "OperationLookup",
    "Overloaded",
    "OwnershipLost",
    "PendingOperation",
    "PersistenceUnavailable",
    "Phase",
    "PollReport",
    "PromptPolicy",
    "PromptPresenter",
    "PromptReceipt",
    "PromptRequest",
    "PromptTexts",
    "QuietHours",
    "QuietHoursResolver",
    "QuietRestorePolicy",
    "ReconcileReport",
    "RedisDeploymentAttestation",
    "StorageActivation",
    "StorageMigrationPage",
    "ReplyPromptControls",
    "RuntimeSnapshot",
    "SchemaUnsupported",
    "SessionAuthority",
    "SessionAuthorityUnavailable",
    "coarse_event_sink",
    "SessionExpired",
    "SessionGuard",
    "SessionSnapshot",
    "SystemClock",
    "TelegramPromptPresenter",
    "UnsupportedContext",
    "VersionConflict",
]
