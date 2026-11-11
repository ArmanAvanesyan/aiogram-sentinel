"""Installed-package Idle benchmarks. Results never self-award qualification.

The representative CPU preset uses a fixed external session, policy and draft,
with nine successful touches per activation. Real Redis and combined navigation
measurements are labeled separately. Run final comparisons serially, twice per
engine, using independent environments and this exact driver manifest.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
import time
from uuid import uuid4

if __package__:
    from .support import (
        command_summary,
        counted_redis_type,
        measured_row,
    )
else:
    from support import (
        command_summary,
        counted_redis_type,
        measured_row,
    )

from aiogram_coordination import ExternalSession

from aiogram_idle import (
    ActionReceipt,
    ActivityRegistration,
    ExemptPolicy,
    FlowEligibility,
    IdleConfig,
    IdleConversationKey,
    IdlePolicies,
    IdleRuntime,
    MemoryIdleBackend,
    PromptPolicy,
)
from aiogram_idle.clock import ManualClock

PAYLOAD = {
    "selection": "fixed",
    "values": [1, 2, 3],
    "locale": "en",
    "draft_id": "benchmark-draft",
    "padding": "x" * 128,
}
KEY = IdleConversationKey("benchmark", 123456, 42, 42)
FLOW = ActivityRegistration("form.typing", "draft", "form", PAYLOAD)


class Adapter:
    async def inspect(self, context):
        return FlowEligibility()

    async def resume(self, context, *, operation_id):
        return ActionReceipt()

    async def abandon(self, context, *, reason, operation_id):
        return ActionReceipt(disposition="disarm")

    async def restore(self, context, *, reason, operation_id):
        return ActionReceipt(disposition="disarm")


class Presenter:
    async def show(self, request):
        raise AssertionError("The benchmark never executes idle delivery")

    async def finish(self, request):
        raise AssertionError("The benchmark never executes idle delivery")

    async def strip(self, prompt):
        raise AssertionError("No prompt is created by this preset")


class Authority:
    def __init__(self, clock):
        now = int(clock.now() * 1000)
        self.value = ExternalSession(
            "application-session", "revision-1", now + 86400000, now + 1800000
        )
        self.calls = 0

    async def current(self, key):
        self.calls += 1
        return self.value


def configuration(engine, *, capacity=None, replay=None):
    fields = inspect.signature(IdleConfig).parameters
    kwargs = {"enabled": True}
    if "engine" in fields:
        kwargs["engine"] = engine
    elif engine != "python":
        raise RuntimeError("Published baseline has no Rust engine; no fallback was attempted")
    if capacity is not None:
        kwargs["max_receipts_per_conversation"] = capacity
    if replay is not None:
        kwargs[
            "replay_retention_seconds"
            if "replay_retention_seconds" in fields
            else "recovery_retention_seconds"
        ] = replay
    return IdleConfig(**kwargs)


def memory_backend(config, clock):
    kwargs = {"config": config, "clock": clock}
    if "storage_format" in inspect.signature(MemoryIdleBackend).parameters:
        kwargs["storage_format"] = 3
    return MemoryIdleBackend(**kwargs)


async def initialize(backend, *, external=True):
    if hasattr(backend, "initialize"):
        await backend.initialize()
    authority = Authority(backend.clock) if external else None
    runtime = IdleRuntime(
        backend=backend,
        policies=IdlePolicies({"none": ExemptPolicy(), "draft": PromptPolicy(3600, 600)}),
        adapters={"form": Adapter()},
        presenter=Presenter(),
        namespace="benchmark",
        session_authority=authority,
    )
    await runtime.initialize()
    if external and await backend.storage_format() < 2:
        await backend.activate_storage_format(
            operation_id="benchmark-format2", old_workers_drained=True, dry_run=False
        )
    if not external:
        await runtime.for_conversation(KEY).open_session(
            operation_id="session", lifetime_seconds=86400
        )
    return runtime, authority


async def accept(context, index, activity, *, all_activations=False):
    if activity is None or all_activations or index % 10 == 0:
        return await context.activate(
            FLOW, operation_id=f"operation:{index}", expected=activity.guard if activity else None
        )
    return await context.touch(operation_id=f"operation:{index}", expected=activity.guard)


async def storage_diagnostics(client, backend):
    """Observation after timing; diagnostic Redis calls are never update calls."""
    prefix = backend._store.prefix
    total = 0
    keys = 0
    async for name in client.scan_iter(match=prefix + ":*", count=64):
        keys += 1
        total += int(await client.memory_usage(name) or 0)
    hot = await client.get(backend._store.keys(KEY)[0])
    return {
        "hot_value_bytes": len(hot) if hot else 0,
        "retained_redis_memory_bytes": total,
        "redis_keys": keys,
        "measurement_boundary": "Post-timing SCAN/MEMORY USAGE/GET, excluded from update RTT and latency; includes indexes/coordination/metadata",
    }


async def loop_lag_workload(engine, samples):
    backend = memory_backend(configuration(engine, capacity=2 * samples + 32), ManualClock(1000))
    try:
        runtime, _ = await initialize(backend)
        context = runtime.for_conversation(KEY)
        activity = None
        lag = []

        # A ready task is delayed by one uninterrupted realistic update batch.
        # This is a separate diagnostic, never the representative CPU gate.
        async def sentinel():
            started = time.perf_counter()
            await asyncio.sleep(0)
            lag.append(time.perf_counter() - started)

        task = asyncio.create_task(sentinel())
        await asyncio.sleep(0)
        for index in range(samples):
            activity = await accept(context, index, activity)
        await task
        return {
            "scenario": "memory-event-loop-lag",
            "workload": "memory-event-loop-lag/1",
            "engine": engine,
            "calls": samples,
            "raw_event_loop_lag_seconds": lag,
            "measurement_boundary": "Ready-task delay during uninterrupted update batch, separate from representative CPU timing",
            "qualification": False,
        }
    finally:
        await backend.close()


async def memory_workload(age, engine, samples, repeats):
    cpu = []
    latencies = []
    authority_calls = 0
    for _ in range(repeats):
        backend = memory_backend(
            configuration(engine, capacity=2 * (age + samples) + 32), ManualClock(1000)
        )
        runtime, authority = await initialize(backend)
        context = runtime.for_conversation(KEY)
        activity = None
        for index in range(age):
            activity = await accept(context, index, activity)
        started_cpu = time.process_time()
        for index in range(age, age + samples):
            started = time.perf_counter()
            activity = await accept(context, index, activity)
            latencies.append(time.perf_counter() - started)
        cpu.append(time.process_time() - started_cpu)
        authority_calls += authority.calls
        await backend.close()
        gc.collect()
    return measured_row(
        "memory-activate-touch",
        age,
        engine,
        samples,
        cpu,
        latencies,
        fixture_boundary="fixed 256-byte-class draft; one absolute session; nine touches per activation; retained replay age..age+samples",
        application_authority_calls=authority_calls,
        application_authority_transport="in-process immutable read, no I/O",
        client_round_trips=0,
        lua_calls=0,
    )


async def claim_workload(engine, samples, repeats):
    cpu = []
    latencies = []
    for _ in range(repeats):
        clock = ManualClock(1000)
        backend = memory_backend(configuration(engine), clock)
        for actor in range(1, 17):
            key = IdleConversationKey("claim-benchmark", 123456, actor, actor)
            session = await backend.open_session(
                key, lifetime_seconds=86400, operation_id="session"
            )
            await backend.enter(
                key,
                "form",
                policy_id="draft",
                policy=PromptPolicy(1, 600),
                adapter_key="form",
                params=PAYLOAD,
                session_id=session.session_id,
                expires_at=session.expires_at,
                operation_id="enter",
                enabled=True,
            )
        clock.advance(2)
        started_cpu = time.process_time()
        for _index in range(samples):
            started = time.perf_counter()
            claims = await backend.claim_due(limit=8, lease_seconds=60)
            for claim in claims:
                await backend.release_claim(claim, retry_at=clock.now() + 1)
            clock.advance(1)
            latencies.append(time.perf_counter() - started)
        cpu.append(time.process_time() - started_cpu)
        await backend.close()
    return measured_row(
        "memory-deadline-claims",
        16,
        engine,
        samples,
        cpu,
        latencies,
        fixture_boundary="16 live private conversations, batches of eight due claims/release; clock and entropy remain in Python",
        client_round_trips=0,
        lua_calls=0,
    )


async def admission_trajectory(engine, targets, *, short_replay=False):
    results = []
    for target in targets:
        clock = ManualClock(1000)
        capacity = 32 if short_replay else None
        backend = memory_backend(
            configuration(engine, capacity=capacity, replay=0.01 if short_replay else None), clock
        )
        runtime, _ = await initialize(backend)
        context = runtime.for_conversation(KEY)
        activity = None
        error = None
        completed = 0
        for index in range(target):
            try:
                activity = await accept(context, index, activity, all_activations=True)
                completed += 1
                if short_replay:
                    clock.advance(0.011)
            except Exception as failure:
                error = {
                    "type": type(failure).__name__,
                    "reason": getattr(failure, "reason", None),
                    "request_number": index + 1,
                }
                break
        results.append(
            {
                "scenario": "expired-replay-admission" if short_replay else "default-admission",
                "workload": f"{'expired-replay-admission' if short_replay else 'default-admission'}/{target}",
                "engine": engine,
                "state_age": target,
                "completed": completed,
                "capacity": capacity or 256,
                "error": error,
                "qualification": False,
                "note": "Explicit caller operations after expiry; no claim of forever operation-ID detection or automatic business retry.",
            }
        )
        await backend.close()
    return results


async def redis_backend(url, engine, capacity):
    from aiogram_idle.storage.redis import RedisIdleBackend

    client = counted_redis_type().from_url(url, decode_responses=False)
    await client.ping()
    kwargs = {
        "redis": client,
        "prefix": "idle-benchmark:" + uuid4().hex,
        "config": configuration(engine, capacity=capacity),
    }
    if "storage_format" in inspect.signature(RedisIdleBackend).parameters:
        kwargs["storage_format"] = 3
    backend = RedisIdleBackend(**kwargs)
    await backend.initialize()
    return backend, client


async def cleanup_prefix(client, prefix):
    pending = []
    async for key in client.scan_iter(match=prefix + ":*", count=32):
        pending.append(key)
        if len(pending) == 32:
            await client.unlink(*pending)
            pending = []
    if pending:
        await client.unlink(*pending)


async def redis_workload(url, age, engine, samples):
    backend, client = await redis_backend(url, engine, 2 * (age + samples) + 32)
    try:
        runtime, authority = await initialize(backend)
        context = runtime.for_conversation(KEY)
        activity = None
        for index in range(age):
            activity = await accept(context, index, activity)
        calls = []
        latencies = []
        per_update = []
        started_cpu = time.process_time()
        for index in range(age, age + samples):
            begin = len(client.benchmark_calls)
            started = time.perf_counter()
            activity = await accept(context, index, activity)
            latencies.append(time.perf_counter() - started)
            action = client.benchmark_calls[begin:]
            calls.extend(action)
            per_update.append(len(action))
        cpu = [time.process_time() - started_cpu]
        row = measured_row(
            "redis-activate-touch",
            age,
            engine,
            samples,
            cpu,
            latencies,
            **command_summary(calls),
            per_update_round_trips=per_update,
            application_authority_calls=authority.calls,
            fixture_boundary="Warm backend/schema/scripts; library coordination included; immutable app authority has no I/O",
            qualification=False,
        )
        row["storage_diagnostics"] = await storage_diagnostics(client, backend)
        return row
    finally:
        await backend.close()
        await cleanup_prefix(client, backend._store.prefix)
        await client.aclose()


async def combined_workload(url, age, engine, samples):
    from aiogram_nav import (
        ApplicationPresenter,
        CleanupResult,
        ConversationKey,
        MessageRef,
        Navigation,
        NavigationConfig,
        NavigationRegistry,
        Node,
        RenderResult,
    )

    from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies

    config = configuration(engine, capacity=8 * (age + samples) + 128)
    if url:
        backend, client = await redis_backend(url, engine, 8 * (age + samples) + 128)
    else:
        backend = memory_backend(config, ManualClock(1000))
        client = None
    cleanup_calls = 0

    async def cleanup(request):
        nonlocal cleanup_calls
        cleanup_calls += 1
        return CleanupResult()

    try:
        runtime, _ = await initialize(backend, external=False)
        nav_args = {"history_limit": 3, "max_receipts": 8 * (age + samples) + 128}
        if "engine" in inspect.signature(NavigationConfig).parameters:
            nav_args["engine"] = engine
        registry_args = {
            "roots": {"main"},
            "nodes": [Node("main", renderer="app"), Node("form", parent="main", renderer="app")],
        }
        if "engine" in inspect.signature(NavigationRegistry).parameters:
            registry_args["engine"] = engine
        registry = NavigationRegistry(**registry_args)
        integration = NavigationIntegration(
            idle=runtime,
            registry=registry,
            policies=NodePolicies(default="none", overrides={"form": "draft"}),
            config=NavigationConfig(**nav_args),
        )
        nav = Navigation(
            registry=registry,
            repository=integration.navigation_repository,
            presenter=ApplicationPresenter(cleanup=cleanup),
            namespace="benchmark",
        )
        integration.bind(nav)
        key = ConversationKey("benchmark", 123456, 42, 42)
        context = nav.for_conversation(key)

        async def track(index):
            return await context.track(
                "form",
                params=PAYLOAD,
                rendered=RenderResult(f"view:{index}", (MessageRef(42, index + 1),)),
                operation_id=f"track:{index}",
            )

        for index in range(age):
            await track(index)
        latencies = []
        calls = []
        per_update = []
        started_cpu = time.process_time()
        for index in range(age, age + samples):
            begin = len(client.benchmark_calls) if client else 0
            started = time.perf_counter()
            await track(index)
            latencies.append(time.perf_counter() - started)
            if client:
                action = client.benchmark_calls[begin:]
                calls.extend(action)
                per_update.append(len(action))
        scenario = "redis-track" if url else "memory-track"
        result = measured_row(
            scenario,
            age,
            engine,
            samples,
            [time.process_time() - started_cpu],
            latencies,
            **command_summary(calls),
            per_update_round_trips=per_update,
            application_cleanup_calls=cleanup_calls,
            fixture_boundary="Already-rendered application view; bounded history3; library coordinator included; no Telegram transport",
            qualification=False,
        )
        if client:
            result["storage_diagnostics"] = await storage_diagnostics(client, backend)
            result["deterministic_budget"] = {
                "max_library_round_trips": 20,
                "observed_max": max(per_update),
                "passed": max(per_update) <= 20,
            }
        return result
    finally:
        await backend.close()
        if client:
            await cleanup_prefix(client, backend._store.prefix)
            await client.aclose()
