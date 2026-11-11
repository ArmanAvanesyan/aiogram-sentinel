"""Whole protected dispatcher updates against a dedicated Redis primary."""

from __future__ import annotations

import inspect
import math
import statistics
import time
from datetime import datetime, timezone
from uuid import uuid4

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Chat, Message, Update, User
from redis_metrics import client

from aiogram_nav import (
    ApplicationPresenter,
    CleanupResult,
    ConversationKey,
    Navigation,
    NavigationRegistry,
    Node,
    RenderResult,
)
from aiogram_nav.storage.redis import RedisNavigationRepository


class NoTelegram(BaseSession):
    async def close(self):
        return None

    async def make_request(self, *args, **kwargs):
        raise AssertionError("This probe must not send Telegram requests")

    async def stream_content(self, *args, **kwargs):
        yield b""


def p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def incoming(index, text):
    return Update(
        update_id=index,
        message=Message(
            message_id=index,
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            chat=Chat(id=42, type="private"),
            from_user=User(id=42, is_bot=False, first_name="Benchmark"),
            text=text,
        ),
    )


async def workload(url, engine, age, samples, configuration):
    redis, metrics = client(url)
    prefix = f"benchmark-nav:{uuid4().hex}"
    bot = Bot("123456:ABC", session=NoTelegram())
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    payload = {"selection": "fixed", "values": [1, 2, 3], "locale": "en"}

    async def cleanup(request):
        return CleanupResult()

    kwargs = dict(redis=redis, prefix=prefix, config=configuration(engine, age + samples + 10))
    if "storage_format" in inspect.signature(RedisNavigationRepository).parameters:
        kwargs["storage_format"] = 3
    repo = RedisNavigationRepository(**kwargs)
    result = []
    phase = "bootstrap"
    completed = 0
    try:
        await redis.ping()
        metrics.reset()
        await repo.initialize()
        startup = metrics.snapshot()
        nav = Navigation(
            registry=NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="app")]),
            repository=repo,
            presenter=ApplicationPresenter(cleanup=cleanup),
            namespace="benchmark",
        )
        nav.install(dispatcher)
        app = Router()

        @app.message()
        async def handler(message, nav_context):
            if message.text == "track":
                await nav_context.track(
                    "main",
                    params=payload,
                    rendered=RenderResult(f"v{message.message_id}"),
                    operation_id=f"op{message.message_id}",
                )

        dispatcher.include_router(app)
        context = nav.for_conversation(ConversationKey("benchmark", bot.id, 42, 42))
        phase = "fixture"
        for index in range(age):
            await context.track(
                "main",
                params=payload,
                rendered=RenderResult(f"age-{index}"),
                operation_id=f"age-{index}",
            )
            completed += 1
        for kind in ("noop", "track"):
            phase = kind
            before = await redis.info("commandstats")
            metrics.reset()
            latency, roundtrips, sent, received = [], [], [], []
            cpu = time.process_time_ns()
            for index in range(samples):
                previous = metrics.snapshot()
                started = time.perf_counter_ns()
                await dispatcher.feed_update(bot, incoming(age + index + 1, kind))
                latency.append(time.perf_counter_ns() - started)
                snapshot = metrics.snapshot()
                roundtrips.append(snapshot["responses"] - previous["responses"])
                sent.append(snapshot["sent"] - previous["sent"])
                received.append(snapshot["received"] - previous["received"])
            cpu = (time.process_time_ns() - cpu) / samples
            summary = metrics.snapshot()
            after = await redis.info("commandstats")
            server = {
                name.removeprefix("cmdstat_"): value["calls"] - before.get(name, {}).get("calls", 0)
                for name, value in after.items()
                if value["calls"] > before.get(name, {}).get("calls", 0)
            }
            internal = {
                name: count - summary["commands"].get(name, 0)
                for name, count in server.items()
                if name != "info" and count - summary["commands"].get(name, 0) > 0
            }
            result.append(
                dict(
                    scenario=f"redis-dispatch-{kind}",
                    workload=f"redis-dispatch-{kind}/{age}",
                    process_cpu_seconds=[cpu * samples / 1_000_000_000],
                    median_process_cpu_seconds=cpu * samples / 1_000_000_000,
                    calls=samples,
                    cpu_count=1,
                    update_p95_seconds=p95(latency) / 1_000_000_000,
                    update_sample_count=len(latency),
                    raw_latency_seconds=[value / 1_000_000_000 for value in latency],
                    raw_client_round_trips=roundtrips,
                    raw_sent_bytes=sent,
                    raw_received_bytes=received,
                    engine=engine,
                    state_age=age,
                    storage_format=repo.storage_format,
                    status="measured",
                    samples=samples,
                    fixture_boundary="whole protected handler; fixed payload and zero history growth; owned disposable prefix",
                    median_cpu_ns=cpu,
                    median_ns=statistics.median(latency),
                    p95_ns=p95(latency),
                    median_client_round_trips=statistics.median(roundtrips),
                    p95_client_round_trips=p95(roundtrips),
                    max_client_round_trips=max(roundtrips),
                    median_sent_bytes=statistics.median(sent),
                    p95_sent_bytes=p95(sent),
                    median_received_bytes=statistics.median(received),
                    p95_received_bytes=p95(received),
                    client_commands=summary["commands"],
                    lua_internal_commands=internal,
                    cold_namespace_bootstrap=startup,
                )
            )
        return result
    except Exception as error:
        return [
            dict(
                scenario="redis-dispatch",
                engine=engine,
                state_age=age,
                status="unavailable",
                error_type=type(error).__name__,
                phase=phase,
                completed_fixture_age=completed,
            )
        ]
    finally:
        await dispatcher.fsm.close()
        await repo.close()
        # Only this newly generated, owned benchmark namespace is removed.
        owned = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if owned:
            await redis.delete(*owned)
        await redis.aclose()
        await bot.session.close()
