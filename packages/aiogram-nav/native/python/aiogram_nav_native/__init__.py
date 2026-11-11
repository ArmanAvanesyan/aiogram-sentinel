"""Optional deterministic core; importing this package performs no I/O."""

from ._aiogram_nav_native import (
    API_VERSION,
    ENGINE_VERSION,
    Registry,
    fingerprint_canonical,
    strict_loads,
    token_matches,
    transition_history,
    transition_state,
    validate_json,
)

__all__ = [
    "API_VERSION",
    "ENGINE_VERSION",
    "Registry",
    "fingerprint_canonical",
    "strict_loads",
    "token_matches",
    "transition_history",
    "transition_state",
    "validate_json",
]
