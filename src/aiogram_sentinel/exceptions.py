"""Custom exceptions for aiogram-sentinel."""

from typing import Any


class SentinelError(Exception):
    """Base exception for aiogram-sentinel."""


class ConfigurationError(SentinelError):
    """Raised when configuration is invalid."""


class BackendError(SentinelError):
    """Raised when backend operations fail."""


class BackendConnectionError(BackendError):
    """Raised when backend connection fails."""


class BackendOperationError(BackendError):
    """Raised when backend operation fails."""


class MiddlewareError(SentinelError):
    """Raised when middleware operations fail."""


class RouterError(SentinelError):
    """Raised when router operations fail."""
