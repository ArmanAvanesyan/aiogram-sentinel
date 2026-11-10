"""Idle-compatible facade over shared renewable Redis conversation fencing."""

from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager

from aiogram_coordination import OwnershipLost as SharedOwnershipLost
from aiogram_coordination import RedisCoordinator as SharedRedisCoordinator

from ..errors import ConfigurationError, OwnershipLost, PersistenceUnavailable


class RedisCoordinator(SharedRedisCoordinator):
    """Use shared fencing with the established Idle prefix and error family."""

    configuration_error = ConfigurationError
    ownership_lost_error = OwnershipLost
    persistence_unavailable_error = PersistenceUnavailable

    def __init__(
        self,
        *,
        redis: object,
        prefix: str = "aiogram-idle",
        lease_seconds: float = 30,
        renew_seconds: float = 10,
        wait_seconds: float = 30,
        poll_seconds: float = 0.05,
        io_timeout: float = 5,
    ) -> None:
        super().__init__(
            redis=redis,
            prefix=prefix,
            lease_seconds=lease_seconds,
            renew_seconds=renew_seconds,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            io_timeout=io_timeout,
        )

    @asynccontextmanager
    async def borrowed_fsm(self, key: Hashable) -> AsyncGenerator[None, None]:
        try:
            async with super().borrowed_fsm(key):
                yield
        except SharedOwnershipLost as error:
            raise OwnershipLost("Application FSM ownership lost") from error

    @asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncGenerator[None, None]:
        try:
            async with super().hold(key):
                yield
        except SharedOwnershipLost as error:
            raise OwnershipLost("Application FSM ownership lost") from error
