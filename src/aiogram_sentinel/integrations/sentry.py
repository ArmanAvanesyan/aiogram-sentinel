"""Sentry integration for aiogram-sentinel."""

from __future__ import annotations

import logging
from typing import Any

from ..events import BaseEvent, ErrorEvent, events

logger = logging.getLogger(__name__)

# Import sentry_sdk with proper error handling
try:
    import sentry_sdk  # type: ignore[import-untyped]
    from sentry_sdk.integrations.logging import (  # type: ignore[import-untyped]
        LoggingIntegration,
    )

    _sentry_available = True
except ImportError:
    _sentry_available = False
    # Create dummy objects for runtime
    sentry_sdk = None  # type: ignore
    LoggingIntegration = None  # type: ignore


def use_sentry(
    dsn: str | None = None,
    *,
    environment: str | None = None,
    release: str | None = None,
    send_breadcrumbs: bool = True,
    capture_errors: bool = True,
    performance_tracing: bool = False,
    user_context_resolver: Any | None = None,
    scrubber: Any | None = None,
) -> None:
    """Configure Sentry integration for aiogram-sentinel.

    Args:
        dsn: Sentry DSN (if None, uses SENTRY_DSN environment variable)
        environment: Environment name
        release: Release version
        send_breadcrumbs: Whether to send breadcrumbs for events
        capture_errors: Whether to capture exceptions in error middleware
        performance_tracing: Whether to enable performance tracing
        user_context_resolver: Function to resolve user context for Sentry
        scrubber: Function to scrub sensitive data from events

    Raises:
        RuntimeError: If sentry-sdk is not installed.
    """
    if not _sentry_available:
        raise RuntimeError(
            "sentry-sdk is not installed. Install aiogram-sentinel[sentry] to enable Sentry integration."
        )

    # Initialize Sentry SDK
    assert sentry_sdk is not None  # Type guard for pyright
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[
            LoggingIntegration(  # type: ignore[operator]
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
        traces_sample_rate=1.0 if performance_tracing else 0.0,
        before_send=scrubber,
    )

    # Subscribe to events if breadcrumbs are enabled
    if send_breadcrumbs:
        events.subscribe(ErrorEvent, _sentry_error_breadcrumb)
        # Future: events.subscribe(RateLimitEvent, _sentry_rate_limit_breadcrumb)
        # Future: events.subscribe(DebounceEvent, _sentry_debounce_breadcrumb)

    # Store configuration for middleware use
    _sentry_config = {
        "capture_errors": capture_errors,
        "user_context_resolver": user_context_resolver,
    }


async def _sentry_error_breadcrumb(event: BaseEvent) -> None:
    """Add breadcrumb for error events.

    Args:
        event: Error event
    """
    if not isinstance(event, ErrorEvent):
        return

    try:
        assert sentry_sdk is not None  # Type guard for pyright
        sentry_sdk.add_breadcrumb(
            message=f"Error: {event.error_type}",
            category="error",
            level="error",
            data={
                "error_type": event.error_type,
                "event_type": event.event_type,
                "user_id": event.user_id,
                "chat_id": event.chat_id,
                "locale": event.locale,
                "retry_after": event.retry_after,
            },
        )
    except Exception as e:
        logger.exception("Failed to add Sentry breadcrumb: %s", e)


def capture_exception(exception: Exception, **kwargs: Any) -> None:
    """Capture an exception in Sentry.

    Args:
        exception: Exception to capture
        **kwargs: Additional context
    """
    try:
        assert sentry_sdk is not None  # Type guard for pyright
        sentry_sdk.capture_exception(exception, **kwargs)
    except Exception as e:
        logger.exception("Failed to capture exception in Sentry: %s", e)


def set_user_context(user_id: int | None, chat_id: int | None) -> None:
    """Set user context in Sentry.

    Args:
        user_id: User ID
        chat_id: Chat ID
    """
    try:
        assert sentry_sdk is not None  # Type guard for pyright
        sentry_sdk.set_user(
            {
                "id": user_id,
                "chat_id": chat_id,
            }
        )
    except Exception as e:
        logger.exception("Failed to set Sentry user context: %s", e)
