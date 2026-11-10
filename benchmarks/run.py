"""Installed-package baseline/candidate benchmark; no source-path injection.

Run each engine in an isolated environment on an otherwise idle host. The output
is evidence, not an automatic wall-time acceptance gate.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import importlib.metadata
import inspect
import json
import math
import os
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psutil
from aiogram.types import Chat, Message, User

from aiogram_sentinel import SentinelConfig
from aiogram_sentinel.middlewares.policy_resolver import PolicyResolverMiddleware
from aiogram_sentinel.middlewares.throttling import ThrottlingMiddleware
from aiogram_sentinel.policy import PolicyRegistry
from aiogram_sentinel.scopes import KeyBuilder
from aiogram_sentinel.storage.memory import MemoryDebounce, MemoryRateLimiter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("python", "rust"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument(
        "--redis-url",
        help="Dedicated disposable Redis database; only unique benchmark keys are deleted",
    )
    args = parser.parse_args()
    supported = "engine" in inspect.signature(MemoryRateLimiter).parameters
    if not supported and args.engine != "python":
        parser.error("installed baseline has no Rust engine")
    options = {"engine": args.engine} if supported else {}
    count, repeats, warmups = (5000, 5, 2) if args.quick else (50000, 15, 5)
    results = []

    async def sample(kind: str, latencies: list[float] | None = None) -> None:
        if kind.startswith("redis_"):
            from redis.asyncio import Redis

            from aiogram_sentinel.storage.redis import RedisRateLimiter

            client = Redis.from_url(args.redis_url)
            prefix = f"sentinel-benchmark-{uuid4().hex}"
            rate = RedisRateLimiter(client, prefix)
            try:
                for index in range(1000):
                    await rate.allow(
                        "hot" if "hot" in kind else str(index % 100),
                        1 if "rejected" in kind else 1000000,
                        3600,
                    )
            finally:
                keys = [key async for key in client.scan_iter(match=f"{prefix}:*")]
                if keys:
                    await client.delete(*keys)
                await client.aclose()
            return
        rate = MemoryRateLimiter(**options)
        debounce = MemoryDebounce(**options)
        if "rejected" in kind:
            await rate.allow("hot", 1, 3600)
            await debounce.seen("hot", 3600, "fingerprint")
        keys = [f"user:{index}" for index in range(1000)]
        if kind == "middleware_fake_io":
            cfg = SentinelConfig(throttling_default_max=1000000)
            resolver = PolicyResolverMiddleware(PolicyRegistry(), cfg)
            throttle = ThrottlingMiddleware(rate, cfg, KeyBuilder("bench"))
            event = Message(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=Chat(id=1, type="private"),
                from_user=User(id=1, is_bot=False, first_name="bench"),
                text="hello",
            )

            async def application(event, data):
                # Yield once to model an application/fake Telegram I/O boundary.
                await asyncio.sleep(0)

            async def limited(event, data):
                return await throttle(application, event, data)

            for _ in range(count if latencies is None else 1000):
                start = time.perf_counter()
                await resolver(limited, event, {})
                if latencies is not None:
                    latencies.append(time.perf_counter() - start)
            return
        if kind == "rate_concurrent":
            await asyncio.gather(
                *(rate.allow(keys[i % 1000], 1000000, 3600) for i in range(count))
            )
        else:
            for index in range(count):
                key = keys[index % 1000] if "many" in kind else "hot"
                if kind.startswith("rate"):
                    await rate.allow(key, 1 if "rejected" in kind else 1000000, 3600)
                else:
                    await debounce.seen(
                        key, 3600, str(index) if "accepted" in kind else "fingerprint"
                    )

    workloads = (
        "rate_accepted_hot",
        "rate_rejected_hot",
        "rate_accepted_many",
        "debounce_rejected_hot",
        "debounce_accepted_many",
        "rate_concurrent",
        "middleware_fake_io",
    ) + (("redis_rejected_hot", "redis_accepted_many") if args.redis_url else ())
    for kind in workloads:
        for _ in range(warmups):
            asyncio.run(sample(kind))
        wall, cpu = [], []
        for _ in range(repeats):
            gc.collect()
            start, start_cpu = time.perf_counter(), time.process_time()
            asyncio.run(sample(kind))
            cpu.append(time.process_time() - start_cpu)
            wall.append(time.perf_counter() - start)
        results.append(
            {
                "workload": kind,
                "calls": 1000 if kind.startswith("redis_") else count,
                "warmups": warmups,
                "repeats": repeats,
                "wall_seconds": wall,
                "process_cpu_seconds": cpu,
                "median_seconds": statistics.median(wall),
                "p95_seconds": sorted(wall)[math.ceil(len(wall) * 0.95) - 1],
                "percentile_method": "nearest-rank; batch durations, not update latency",
                "median_process_cpu_seconds": statistics.median(cpu),
                "rss_bytes": psutil.Process().memory_info().rss,
            }
        )
        if kind == "middleware_fake_io":
            latencies: list[float] = []
            asyncio.run(sample(kind, latencies))
            results[-1]["update_latency_seconds"] = latencies
            results[-1]["update_p95_seconds"] = sorted(latencies)[
                math.ceil(len(latencies) * 0.95) - 1
            ]
            results[-1]["update_sample_count"] = len(latencies)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    try:
        rust = subprocess.check_output(["rustc", "--version"], text=True).strip()
    except OSError:
        rust = None
    report = {
        "package": "aiogram-sentinel",
        "version": importlib.metadata.version("aiogram-sentinel"),
        "engine": args.engine,
        "commit": commit,
        "python": platform.python_version(),
        "rust": rust,
        "os": platform.platform(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "seed": 137,
        "qualification": False,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
