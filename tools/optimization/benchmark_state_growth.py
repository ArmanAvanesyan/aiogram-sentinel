"""Measure installed Nav/Idle state growth without Telegram or source injection.
Use a fresh process/environment per artifact and mode. Results are exploratory, not native-engine qualification. Redis commands are client invocations, NOT TCP
round trips or Lua-internal command counts. Only this run's unique prefix is read
or deleted; Redis format activation applies only to that disposable namespace.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.metadata
import importlib.util
import inspect
import json
import os
import platform
import resource
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

_helper_path = Path(__file__).with_name("state_growth_metrics.py")
_helper_spec = importlib.util.spec_from_file_location("state_growth_metrics", _helper_path)
assert _helper_spec is not None and _helper_spec.loader is not None
_helper = importlib.util.module_from_spec(_helper_spec)
_helper_spec.loader.exec_module(_helper)
CommandMetrics, LagProbe, counting_redis = (
    _helper.CommandMetrics,
    _helper.LagProbe,
    _helper.counting_redis,
)

plain = _helper.plain


def verify_artifacts(mode):
    names = ["aiogram-nav"] if mode == "nav" else ["aiogram-idle"]
    if mode == "combined":
        names.append("aiogram-nav")
    names.extend(["aiogram", "aiogram-coordination"])
    result = []
    for name in names:
        distribution = importlib.metadata.distribution(name)
        module = importlib.import_module(name.replace("-", "_"))
        location = Path(module.__file__).resolve()
        direct = json.loads(distribution.read_text("direct_url.json") or "{}")
        if direct.get("dir_info", {}).get("editable") or "site-packages" not in location.parts:
            raise RuntimeError(
                f"{name} must be installed from an artifact, not checkout/editable source"
            )
        result.append(
            {
                "name": name,
                "version": distribution.version,
                "module": str(location),
                "direct_url": direct,
            }
        )
    return result


def config(cls, *, engine, **kwargs):
    if "engine" in inspect.signature(cls).parameters:
        kwargs["engine"] = engine
    elif engine != "python":
        raise RuntimeError("Installed baseline does not support explicit native engine selection")
    return cls(**kwargs)


async def activate_format(store, target, *, staged=False):
    if hasattr(store, "initialize"):
        await store.initialize()
    for version in range(2, target + 1) if staged else (target,):
        await store.activate_storage_format(
            operation_id=f"benchmark-format-{version}",
            expected=version - 1 if staged else 1,
            target=version,
            old_workers_drained=True,
            dry_run=False,
        )


class FakeScreens:
    replay_safe = True

    async def render(self, request):
        from aiogram_nav import RenderResult

        return RenderResult(request.view_id)

    async def cleanup(self, request):
        return None


class FakeIdleFlow:
    replay_safe = True

    async def inspect(self, context):
        from aiogram_idle import FlowEligibility

        return FlowEligibility()

    async def resume(self, context, *, operation_id):
        from aiogram_idle import ActionReceipt

        return ActionReceipt(operation_id=operation_id)

    async def abandon(self, context, *, reason, operation_id):
        from aiogram_idle import ActionReceipt

        return ActionReceipt(operation_id=operation_id, disposition="disarm")

    async def restore(self, context, *, reason, operation_id):
        from aiogram_idle import ActionReceipt

        return ActionReceipt(operation_id=operation_id, disposition="disarm")


class NoTelegram:
    async def show(self, request):
        raise AssertionError("This benchmark must not send prompts")

    async def finish(self, request):
        raise AssertionError("This benchmark must not send outcomes")

    async def strip(self, receipt):
        raise AssertionError("This benchmark must not edit Telegram messages")


class Authority:
    def __init__(self):
        from aiogram_coordination import ExternalSession

        self.value = ExternalSession(
            "benchmark-session", "fixed-revision", int((time.time() + 28800) * 1000)
        )

    async def current(self, key):
        return self.value


async def fixture(args, client, prefix):
    authority = Authority() if args.external_sessions else None
    params = {"payload": "0123456789abcdef"}
    if args.mode in {"idle", "combined"}:
        from aiogram_idle import ExemptPolicy, IdleConfig, IdlePolicies, IdleRuntime
        from aiogram_idle.storage.memory import MemoryIdleBackend

        settings = config(
            IdleConfig,
            engine=args.engine,
            enabled=False,
            **({"max_receipts_per_conversation": args.receipt_limit} if args.receipt_limit else {}),
        )
        if client is None:
            store = MemoryIdleBackend(config=settings)
        else:
            from aiogram_idle.storage.redis import RedisIdleBackend

            store = RedisIdleBackend(redis=client, prefix=prefix, config=settings)
        target = 3 if args.storage_format3 else 2 if authority else None
        if target:
            await activate_format(store, target, staged=True)
        runtime = IdleRuntime(
            backend=store,
            config=settings,
            namespace="state-growth",
            policies=IdlePolicies({"none": ExemptPolicy()}),
            adapters={"flow": FakeIdleFlow()},
            presenter=NoTelegram(),
            session_authority=authority,
        )
        await runtime.initialize()
    if args.mode in {"nav", "combined"}:
        from aiogram_nav import (
            ConversationKey,
            Navigation,
            NavigationConfig,
            NavigationRegistry,
            Node,
        )

        nav_config = config(
            NavigationConfig,
            engine=args.engine,
            history_limit=20,
            **({"max_receipts": args.receipt_limit} if args.receipt_limit else {}),
        )
        registry = NavigationRegistry(
            roots={"main"},
            nodes=[
                Node("main", renderer="screen"),
                Node("panel", parent="main", renderer="screen"),
            ],
        )
        if args.mode == "combined":
            from aiogram_idle.integrations.nav import (
                NavigationIntegration,
                NodePolicies,
            )

            integration = NavigationIntegration(
                idle=runtime,
                registry=registry,
                config=nav_config,
                policies=NodePolicies(default="none"),
            )
            repository = integration.navigation_repository
        else:
            if client is None:
                from aiogram_nav.storage.memory import MemoryNavigationRepository

                repository = MemoryNavigationRepository(config=nav_config)
            else:
                from aiogram_nav.storage.redis import RedisNavigationRepository

                repository = RedisNavigationRepository(
                    redis=client, prefix=prefix, config=nav_config
                )
            store = repository
            target = 3 if args.storage_format3 else 2 if authority else None
            if target:
                await activate_format(store, target)
        nav = Navigation(
            registry=registry,
            repository=repository,
            presenter=FakeScreens(),
            namespace="state-growth",
            config=nav_config,
            session_authority=authority if args.mode == "nav" else None,
        )
        if args.mode == "combined":
            integration.bind(nav)
        context = nav.for_conversation(ConversationKey("state-growth", 1, 42, 42))

        async def step(number):
            from aiogram_nav import RenderResult

            return await context.track(
                "main" if number % 2 else "panel",
                params=params,
                rendered=RenderResult(f"view-{number}"),
                operation_id=f"track-{number}",
            )

        async def snapshot():
            return await context.current()

        settings = nav_config if args.mode == "nav" else settings
    else:
        from aiogram_idle import ActivityRegistration, IdleConversationKey

        context = runtime.for_conversation(IdleConversationKey("state-growth", 1, 42, 42))
        if not authority:
            await context.open_session(operation_id="session", lifetime_seconds=28800)
        registration = ActivityRegistration("form.entry", "none", "flow", params=params)
        current = None
        if args.idle_operation == "touch":
            current = await context.activate(registration, operation_id="initial-activation")

        async def step(number):
            nonlocal current
            if args.idle_operation == "touch":
                current = await context.touch(
                    expected=current.guard, operation_id=f"touch-{number}"
                )
            else:
                current = await context.activate(
                    registration,
                    expected=current.guard if current else None,
                    operation_id=f"activate-{number}",
                )
            return current

        async def snapshot():
            return await context.current()

    return store, step, snapshot, plain(settings)


redis_state = _helper.redis_state


async def benchmark(args):
    artifacts = verify_artifacts(args.mode)
    metrics = CommandMetrics()
    prefix = "aiogram-state-growth:" + uuid4().hex
    client = counting_redis(args.redis_url, metrics) if args.redis_url else None
    endpoint = urlsplit(args.redis_url) if args.redis_url else None
    output = {
        "schema_version": 1,
        "qualification": False,
        "metadata": {
            "metrics_sha256": hashlib.sha256(_helper_path.read_bytes()).hexdigest(),
            "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "mode": args.mode,
            "engine": args.engine,
            "backend": "redis" if client else "memory",
            "external_sessions": args.external_sessions,
            "idle_operation": args.idle_operation,
            "receipt_limit_override": args.receipt_limit,
            "requested_checkpoints": args.screens,
            "artifacts": artifacts,
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "cpu": platform.processor(),
            "cpu_count": os.cpu_count(),
            "prefix": prefix,
            "redis_endpoint": {
                "host": endpoint.hostname,
                "port": endpoint.port,
                "db": endpoint.path,
            }
            if endpoint
            else None,
            "history_limit": 20,
            "parameter_payload_bytes": 16,
            "parameters_json_bytes": 30,
            "real_telegram": False,
            "storage_format3": args.storage_format3,
            "tracemalloc_enabled": args.trace_memory,
            "rss_measurement": "process peak RSS; platform getrusage units normalized to bytes",
            "timing_excludes_state_inspection": True,
            "command_measurement": "client invocations and computed RESP2 requests; not TCP round trips, replies, retries or Lua subcommands",
            "started_at": time.time(),
        },
        "checkpoints": [],
        "outcome": "initializing",
    }

    def save():
        args.output.write_text(json.dumps(output, indent=2) + "\n")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    probe, store, lag_task = LagProbe(), None, None
    try:
        store, step, snapshot, settings = await fixture(args, client, prefix)
        output["metadata"]["config"] = settings
        if client:
            output["metadata"]["redis_version"] = (await client.info("server"))["redis_version"]
        client_metrics = metrics
        initial = metrics.snapshot()
        lag_task = asyncio.create_task(probe.run())
        await asyncio.sleep(0)
        if args.trace_memory:
            tracemalloc.start()
        cpu_total = wall_total = 0.0
        output["outcome"] = "running"
        for number in range(1, max(args.screens) + 1):
            cpu, wall = time.process_time(), time.perf_counter()
            try:
                await step(number)
            except Exception as error:  # noqa: BLE001 - record library capacity/failure boundaries
                output.update(
                    outcome="stopped",
                    failed_operation=number,
                    exception_type=type(error).__name__,
                )
                break
            await asyncio.sleep(0)  # expose in-process CPU stalls to the lag observer
            cpu_total += time.process_time() - cpu
            wall_total += time.perf_counter() - wall
            if number in args.screens:
                cumulative = client_metrics.snapshot()
                command_values = {
                    key: cumulative[key] - initial[key]
                    for key in cumulative
                    if key != "command_histogram"
                }
                command_values["command_histogram"] = dict(
                    Counter(cumulative["command_histogram"]) - Counter(initial["command_histogram"])
                )
                row = {
                    "operations": number,
                    "wall_seconds": wall_total,
                    "process_cpu_seconds": cpu_total,
                    "client_commands": command_values,
                    "event_loop_lag": probe.report(),
                }
                probe.generation += 1
                with client_metrics.paused():
                    value = await snapshot()
                    row["public_snapshot_json_bytes"] = len(
                        json.dumps(plain(value), separators=(",", ":")).encode()
                    )
                    row["current_history_size"] = (
                        len(getattr(getattr(value, "snapshot", value), "history", ()))
                        if value
                        else 0
                    )
                    row["traced_current_bytes"], row["traced_peak_bytes"] = (
                        tracemalloc.get_traced_memory() if args.trace_memory else (None, None)
                    )
                    row["process_peak_rss_bytes"] = resource.getrusage(
                        resource.RUSAGE_SELF
                    ).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
                    if client:
                        row.update(await redis_state(client, prefix))
                probe.generation += 1
                output["checkpoints"].append(row)
                save()
        else:
            output["outcome"] = "completed"
    except Exception as error:  # noqa: BLE001 - record library capacity/failure boundaries
        output.update(outcome="setup_failed", exception_type=type(error).__name__)
    finally:
        tracemalloc.stop()
        if lag_task:
            lag_task.cancel()
            await asyncio.gather(lag_task, return_exceptions=True)
        if store:
            await store.close()
        if client:
            with metrics.paused():
                keys = [key async for key in client.scan_iter(match=prefix + ":*", count=100)]
                for offset in range(0, len(keys), 100):
                    await client.delete(*keys[offset : offset + 100])
            await client.aclose()
        output["metadata"]["finished_at"] = time.time()
        save()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("nav", "idle", "combined"), required=True)
    parser.add_argument("--engine", choices=("python", "rust"), default="python")
    parser.add_argument("--redis-url")
    parser.add_argument("--screens", nargs="+", type=int, default=[1, 10, 50, 500, 5000])
    parser.add_argument("--idle-operation", choices=("activate", "touch"), default="activate")
    parser.add_argument("--external-sessions", action="store_true")
    parser.add_argument("--storage-format3", action="store_true")
    parser.add_argument("--receipt-limit", type=int)
    parser.add_argument("--trace-memory", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if any(value < 1 for value in args.screens) or (
        args.receipt_limit is not None and args.receipt_limit < 1
    ):
        parser.error("screens must be positive")
    args.screens = sorted(set(args.screens))
    result = asyncio.run(benchmark(args))
    print(json.dumps({"outcome": result["outcome"], "output": str(args.output)}))
    return 0 if result["outcome"] in {"completed", "stopped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
