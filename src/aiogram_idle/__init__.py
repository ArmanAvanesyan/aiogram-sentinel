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
    SessionExpired,
    UnsupportedContext,
    VersionConflict,
)
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
from .runtime import IdleRuntime
from .storage.base import IdleBackend
from .storage.memory import MemoryIdleBackend
from .storage.state import OperationLookup

try:
    __version__ = version("aiogram-idle")
except PackageNotFoundError:  # Allow direct source imports before installation.
    __version__ = "0+unknown"
__all__ = [
    "ActionReceipt",
    "ActivityConflict",
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
    "ReplyPromptControls",
    "RuntimeSnapshot",
    "SchemaUnsupported",
    "SessionAuthority",
    "SessionExpired",
    "SessionGuard",
    "SessionSnapshot",
    "SystemClock",
    "TelegramPromptPresenter",
    "UnsupportedContext",
    "VersionConflict",
]
