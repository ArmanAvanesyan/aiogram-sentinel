"""Actual Dispatcher no-op measurements, including library coordination."""

from __future__ import annotations

import inspect
import time
from datetime import datetime, timezone

if __package__:
    from .support import command_summary, counted_redis_type, measured_row
    from .workloads import PAYLOAD, cleanup_prefix, initialize, redis_backend
else:
    from support import command_summary, counted_redis_type, measured_row
    from workloads import PAYLOAD, cleanup_prefix, initialize, redis_backend


async def workload(url, engine, samples):
    from aiogram import Bot, Dispatcher, Router
    from aiogram.client.session.base import BaseSession
    from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
    from aiogram.types import Chat, Message, Update, User
    from aiogram_nav import (
        ApplicationPresenter,
        CleanupResult,
        ConversationKey,
        InputBindings,
        MessageRef,
        Navigation,
        NavigationConfig,
        NavigationRegistry,
        Node,
        RenderResult,
        ReplyEntry,
    )

    from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies

    class NoNetwork(BaseSession):
        async def make_request(self, *args, **kwargs):
            raise AssertionError("No Telegram call belongs to the no-op preset")

        async def close(self):
            pass

        async def stream_content(self, *args, **kwargs):
            raise AssertionError("No Telegram stream belongs to the no-op preset")
            yield b""  # pragma: no cover: satisfies the async-generator contract

    backend, client = await redis_backend(url, engine, 8 * samples + 128)
    fsm = counted_redis_type().from_url(url, decode_responses=False)
    dispatcher = Dispatcher(
        storage=RedisStorage(
            redis=fsm,
            key_builder=DefaultKeyBuilder(prefix=backend._store.prefix + ":fsm", with_bot_id=True),
        ),
        disable_fsm=True,
    )
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=NoNetwork())
    try:
        runtime, _ = await initialize(backend, external=False)
        kwargs = {"history_limit": 3, "max_receipts": 8 * samples + 128}
        if "engine" in inspect.signature(NavigationConfig).parameters:
            kwargs["engine"] = engine
        registry_kwargs = {
            "roots": {"main"},
            "nodes": [Node("main", renderer="app"), Node("form", parent="main", renderer="app")],
        }
        if "engine" in inspect.signature(NavigationRegistry).parameters:
            registry_kwargs["engine"] = engine
        registry = NavigationRegistry(**registry_kwargs)

        async def cleanup(request):
            return CleanupResult()

        integration = NavigationIntegration(
            idle=runtime,
            registry=registry,
            policies=NodePolicies(default="none", overrides={"form": "draft"}),
            config=NavigationConfig(**kwargs),
        )
        nav = Navigation(
            registry=registry,
            repository=integration.navigation_repository,
            presenter=ApplicationPresenter(cleanup=cleanup),
            namespace="benchmark",
            bot=bot,
        )
        nav.bind(InputBindings([ReplyEntry("form", "Go", target="form")]))
        integration.install(dispatcher, navigation=nav, lifecycle=False)
        router = Router()

        @router.message()
        async def handler(message):
            return None

        dispatcher.include_router(router)
        key = ConversationKey("benchmark", 123456, 42, 42)
        await nav.for_conversation(key).track(
            "form",
            params=PAYLOAD,
            rendered=RenderResult("initial", (MessageRef(42, 1),)),
            operation_id="initial",
        )

        def update(index):
            return Update(
                update_id=index,
                message=Message(
                    message_id=index,
                    date=datetime.now(timezone.utc),
                    chat=Chat(id=42, type="private"),
                    from_user=User(id=42, is_bot=False, first_name="Benchmark"),
                    text="unmatched no-op text",
                ),
            )

        for index in range(1, 3):
            await dispatcher.feed_update(bot, update(index))
        calls = []
        fsm_calls = []
        latencies = []
        per_update = []
        start_cpu = time.process_time()
        for index in range(3, 3 + samples):
            before = len(client.benchmark_calls)
            before_fsm = len(fsm.benchmark_calls)
            start = time.perf_counter()
            await dispatcher.feed_update(bot, update(index))
            latencies.append(time.perf_counter() - start)
            action = client.benchmark_calls[before:]
            calls.extend(action)
            per_update.append(len(action))
            fsm_calls.extend(fsm.benchmark_calls[before_fsm:])
        return measured_row(
            "redis-dispatcher-noop",
            1,
            engine,
            samples,
            [time.process_time() - start_cpu],
            latencies,
            **command_summary(calls),
            per_update_round_trips=per_update,
            application_fsm=command_summary(fsm_calls),
            fixture_boundary="Real feed_update, unmatched reply binding plus feature router, library lease acquisition/release included; FSM disabled explicitly; no Telegram transport",
            deterministic_budget={
                "max_library_round_trips": 5,
                "observed_max": max(per_update),
                "passed": max(per_update) <= 5,
            },
            qualification=False,
        )
    finally:
        await dispatcher.emit_shutdown()
        await backend.close()
        await cleanup_prefix(client, backend._store.prefix)
        await client.aclose()
        await bot.session.close()
