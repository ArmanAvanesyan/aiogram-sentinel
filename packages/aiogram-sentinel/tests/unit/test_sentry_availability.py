"""Optional SDK guards must remain active under optimized Python."""

import pytest

from aiogram_sentinel.events import ErrorEvent
from aiogram_sentinel.integrations import sentry


def test_setup_rejects_missing_sdk_despite_availability_flag(monkeypatch):
    monkeypatch.setattr(sentry, "_sentry_available", True)
    monkeypatch.setattr(sentry, "sentry_sdk", None)
    with pytest.raises(RuntimeError, match=r"aiogram-sentinel\[sentry\]"):
        sentry.use_sentry()


def test_best_effort_helpers_log_missing_sdk(monkeypatch, caplog):
    monkeypatch.setattr(sentry, "sentry_sdk", None)
    sentry.capture_exception(ValueError("example"))
    sentry.set_user_context(1, 2)
    assert "Failed to capture exception in Sentry" in caplog.text
    assert "Failed to set Sentry user context" in caplog.text
    assert "Sentry integration is unavailable" in caplog.text


async def test_breadcrumb_logs_missing_sdk(monkeypatch, caplog):
    monkeypatch.setattr(sentry, "sentry_sdk", None)
    await sentry._sentry_error_breadcrumb(
        ErrorEvent("ValueError", "example", "message", 1, 2, "en")
    )
    assert "Failed to add Sentry breadcrumb" in caplog.text
    assert "Sentry integration is unavailable" in caplog.text
