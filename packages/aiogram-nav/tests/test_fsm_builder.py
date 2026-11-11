"""Known external FSM key builders must preserve the normalized identity."""

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram_nav import (
    ConfigurationError,
    MemoryNavigationRepository,
    Navigation,
    NavigationRegistry,
    Node,
    ScreenSpec,
    TextPresenter,
)
from tests.test_examples import RecordingSession


# Exercise the known-storage adapter contract without installing Redis or opening
# a Redis connection. Actual navigation Redis storage remains outside this slice.
class RedisStorage(MemoryStorage):
    __module__ = "aiogram.fsm.storage.redis"

    def __init__(self, builder):
        super().__init__()
        self.key_builder = builder


@pytest.mark.parametrize("include_bot", [False, True])
async def test_known_fsm_builder_must_encode_bot_identity(include_bot):
    bot = Bot("123456:ABC", session=RecordingSession())
    dispatcher = Dispatcher(storage=RedisStorage(DefaultKeyBuilder(with_bot_id=include_bot)))

    async def screen(request):
        return ScreenSpec("Main")

    nav = Navigation(
        registry=NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="main")]),
        repository=MemoryNavigationRepository(),
        presenter=TextPresenter({"main": screen}, bot),
    )
    before = list(dispatcher.update.outer_middleware)
    try:
        if include_bot:
            nav.install(dispatcher)
        else:
            with pytest.raises(ConfigurationError, match="with_bot_id"):
                nav.install(dispatcher)
            assert list(dispatcher.update.outer_middleware) == before
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
