"""Public API for error handling functionality."""

from .events import ErrorEvent
from .middlewares.errors import ErrorConfig, ErrorHandlingMiddleware

__all__ = [
    "ErrorConfig",
    "ErrorEvent",
    "ErrorHandlingMiddleware",
]
