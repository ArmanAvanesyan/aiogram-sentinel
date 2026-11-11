"""Optional deterministic core; importing performs no I/O or library fallback."""

from ._aiogram_idle_native import (
    API_VERSION,
    ENGINE_VERSION,
    DeadlineCore,
    OwnershipLost,
    activity_guard,
    claim_guard,
    fingerprint_canonical,
    phase_transition,
    receipt_admission,
    session_guard,
)

__all__ = [
    "API_VERSION",
    "ENGINE_VERSION",
    "DeadlineCore",
    "OwnershipLost",
    "activity_guard",
    "claim_guard",
    "fingerprint_canonical",
    "phase_transition",
    "receipt_admission",
    "session_guard",
]
