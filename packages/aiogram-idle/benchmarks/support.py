"""Measurement helpers: payload bytes are estimates; server CPU is not RTT time."""

from __future__ import annotations

import hashlib
import importlib.metadata
import math
import platform
import statistics
import sys
import time
from collections import Counter
from pathlib import Path


def percentile(values, fraction=0.95):
    if not values:
        return None
    return sorted(values)[math.ceil(fraction * len(values)) - 1]


def measured_row(scenario, age, engine, samples, cpu, latencies, **extra):
    return dict(
        scenario=scenario,
        workload=f"{scenario}/{age}",
        engine=engine,
        state_age=age,
        calls=samples,
        process_cpu_seconds=cpu,
        median_process_cpu_seconds=statistics.median(cpu) if cpu else None,
        cpu_count=len(cpu),
        raw_latency_seconds=latencies,
        update_p95_seconds=percentile(latencies),
        update_sample_count=len(latencies),
        median_cpu_ns=statistics.median(cpu) * 1e9 / samples if cpu else None,
        **extra,
    )


def payload_bytes(value):
    if isinstance(value, bytes):
        return len(value)
    return len(str(value).encode("utf-8", errors="strict"))


def counted_redis_type():
    from redis.asyncio import Redis

    class CountedRedis(Redis):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.benchmark_calls = []

        async def execute_command(self, *args, **kwargs):
            started = time.perf_counter()
            try:
                result = await super().execute_command(*args, **kwargs)
            finally:
                self.benchmark_calls.append(
                    {
                        "command": str(args[0]).upper(),
                        "argument_bytes": sum(payload_bytes(value) for value in args),
                        "elapsed_seconds": time.perf_counter() - started,
                    }
                )
            return result

    return CountedRedis


def command_summary(calls):
    commands = Counter(value["command"] for value in calls)
    return {
        "client_round_trips": len(calls),
        "client_commands": dict(commands),
        "lua_calls": sum(commands[name] for name in ("EVAL", "EVALSHA")),
        "direct_commands": sum(
            count for name, count in commands.items() if name not in {"EVAL", "EVALSHA"}
        ),
        "argument_payload_bytes": sum(value["argument_bytes"] for value in calls),
        "lua_server_cpu_seconds": None,
        "lua_time_note": "Client elapsed time includes network/client overhead; no server CPU attribution is claimed.",
    }


def provenance(package="aiogram-idle"):
    import aiogram_idle

    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
    except ImportError:
        rss = None
    dist = importlib.metadata.distribution(package)
    direct = dist.read_text("direct_url.json")
    return {
        "package": package,
        "package_version": dist.version,
        "installed_version": dist.version,
        "module_file": aiogram_idle.__file__,
        "direct_url": direct,
        "python": sys.version,
        "os": platform.platform(),
        "cpu": platform.processor(),
        "rss_peak_bytes": rss,
    }


def driver_manifest():
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in Path(__file__).parent.glob("*.py")
    }
