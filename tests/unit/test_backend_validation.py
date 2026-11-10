"""Reject invalid protocol inputs before mutating either storage backend."""

import pytest

from aiogram_sentinel.exceptions import ConfigurationError
from aiogram_sentinel.storage.memory import MemoryDebounce, MemoryRateLimiter


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, -1, True, 2**31, 0.5, float("nan")])
async def test_invalid_limits(value):
    limiter = MemoryRateLimiter()
    with pytest.raises(ConfigurationError):
        await limiter.allow("key", 1, value)
    with pytest.raises(ConfigurationError):
        await limiter.get_remaining("key", value, 1)
    with pytest.raises(ConfigurationError):
        await MemoryDebounce().seen("key", value, "fingerprint")
