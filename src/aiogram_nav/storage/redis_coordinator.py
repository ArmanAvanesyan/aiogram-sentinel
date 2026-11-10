"""Nav-compatible renewable Redis coordination; implementation is shared."""

from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager

from aiogram_coordination import OwnershipLost as SharedOwnershipLost
from aiogram_coordination import RedisCoordinator as SharedRedisCoordinator

from ..errors import ConfigurationError, OwnershipLost, PersistenceUnavailable


class RedisCoordinator(SharedRedisCoordinator):
    configuration_error = ConfigurationError
    ownership_lost_error = OwnershipLost
    persistence_unavailable_error = PersistenceUnavailable

    def __init__(self, *, redis: object, prefix: str = "aiogram-nav", **options: float) -> None:
        super().__init__(redis=redis, prefix=prefix, **options)

    @asynccontextmanager
    async def borrowed_fsm(self, key: Hashable) -> AsyncGenerator[None, None]:
        try:
            async with super().borrowed_fsm(key):
                yield
        except SharedOwnershipLost as error:
            raise OwnershipLost(str(error)) from error

    @asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncGenerator[None, None]:
        try:
            async with super().hold(key):
                yield
        except SharedOwnershipLost as error:
            raise OwnershipLost(str(error)) from error
