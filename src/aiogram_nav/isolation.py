"""Compatibility facades over the shared task-scoped coordination package."""

from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager

from aiogram_coordination import AiogramMemoryCoordinator as SharedAiogramCoordinator
from aiogram_coordination import MemoryCoordinator as MemoryCoordinator
from aiogram_coordination import OwnershipLost as SharedOwnershipLost

from .errors import ConfigurationError, OwnershipLost


class AiogramMemoryCoordinator(SharedAiogramCoordinator):
    configuration_error = ConfigurationError
    ownership_lost_error = OwnershipLost

    @asynccontextmanager
    async def borrowed(self, key: Hashable) -> AsyncGenerator[None, None]:
        try:
            async with super().borrowed(key):
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
