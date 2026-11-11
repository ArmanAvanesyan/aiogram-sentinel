"""Reproducible installed-distribution CPU/latency probes; no source-path injection."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

from aiogram_nav import (
    ApplicationPresenter,
    CleanupResult,
    ConversationKey,
    ManualClock,
    MemoryNavigationRepository,
    Navigation,
    NavigationConfig,
    NavigationRegistry,
    Node,
    RenderResult,
)


def percentile(values, fraction=0.95):
    return sorted(values)[math.ceil(fraction * len(values)) - 1]


def configuration(engine, count):
    kwargs = dict(max_receipts=count, history_limit=3, session_seconds=86400)
    if "engine" in inspect.signature(NavigationConfig).parameters:
        kwargs["engine"] = engine
    elif engine != "python":
        raise RuntimeError("The published baseline does not implement the Rust engine")
    return NavigationConfig(**kwargs)


async def workload(age, engine, samples, repeats):
    cpu, latencies = [], []
    payload = {"selection": "fixed", "values": [1, 2, 3], "locale": "en"}
    key = ConversationKey("benchmark", 1, 2, 2)

    async def cleanup(request):
        return CleanupResult()

    for _repeat in range(repeats):
        config = configuration(engine, age + samples + 10)
        repo = MemoryNavigationRepository(config=config, clock=ManualClock(1000))
        registry_options = (
            {"engine": engine}
            if "engine" in inspect.signature(NavigationRegistry).parameters
            else {}
        )
        nav = Navigation(
            registry=NavigationRegistry(
                roots={"main"}, nodes=[Node("main", renderer="app")], **registry_options
            ),
            repository=repo,
            presenter=ApplicationPresenter(cleanup=cleanup),
            namespace="benchmark",
        )
        context = nav.for_conversation(key)
        for index in range(age):
            await context.track(
                "main",
                params=payload,
                rendered=RenderResult(f"age-{index}"),
                operation_id=f"age-{index}",
            )
        started_cpu = time.process_time_ns()
        for index in range(samples):
            started = time.perf_counter_ns()
            await context.track(
                "main",
                params=payload,
                rendered=RenderResult(f"sample-{index}"),
                operation_id=f"sample-{index}",
            )
            latencies.append(time.perf_counter_ns() - started)
        cpu.append((time.process_time_ns() - started_cpu) / 1_000_000_000)
    return dict(
        scenario="memory-track",
        workload=f"memory-track/{age}",
        process_cpu_seconds=cpu,
        median_process_cpu_seconds=statistics.median(cpu),
        calls=samples,
        update_p95_seconds=percentile(latencies) / 1_000_000_000,
        update_sample_count=len(latencies),
        raw_latency_seconds=[value / 1_000_000_000 for value in latencies],
        engine=engine,
        state_age=age,
        fixture_boundary="fixed payload; zero history growth; retained receipts age..age+samples",
        samples=samples,
        cpu_count=len(cpu),
        repeats=repeats,
        median_cpu_ns=statistics.median(cpu) * 1_000_000_000 / samples,
        median_ns=statistics.median(latencies),
        p95_ns=percentile(latencies),
        client_round_trips=0,
        lua_internal_commands=0,
        bytes_transferred=0,
    )


def registry_workload(size, engine, calls, repeats):
    nodes = [Node("main", renderer="app")]
    nodes.extend(
        Node(f"n{i}", parent="main" if i == 0 else f"n{i - 1}", renderer="app")
        for i in range(size - 1)
    )
    kwargs = dict(roots={"main"}, nodes=nodes)
    if "engine" in inspect.signature(NavigationRegistry).parameters:
        kwargs["engine"] = engine
    latencies, cpu = [], []
    for _ in range(repeats):
        start_cpu = time.process_time_ns()
        for _ in range(calls):
            start = time.perf_counter_ns()
            registry = NavigationRegistry(**kwargs)
            assert registry.root_for(nodes[-1].id) == "main"
            latencies.append(time.perf_counter_ns() - start)
        cpu.append((time.process_time_ns() - start_cpu) / 1_000_000_000)
    return dict(
        scenario="registry-compile",
        workload=f"registry-compile/{size}",
        engine=engine,
        nodes=size,
        samples=len(latencies),
        calls=calls,
        cpu_count=len(cpu),
        process_cpu_seconds=cpu,
        median_process_cpu_seconds=statistics.median(cpu),
        update_p95_seconds=percentile(latencies) / 1_000_000_000,
        update_sample_count=len(latencies),
        raw_latency_seconds=[value / 1_000_000_000 for value in latencies],
        fixture_boundary="prebuilt immutable Node inputs; includes native JSON boundary",
        median_cpu_ns=statistics.median(cpu) * 1_000_000_000 / calls,
        median_ns=statistics.median(latencies),
        p95_ns=percentile(latencies),
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("python", "rust"), default="python")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument(
        "--ages",
        nargs="+",
        type=int,
        help="Receipt ages; legacy published baseline defaults to bounded age16",
    )
    parser.add_argument("--registry-sizes", nargs="+", type=int)
    parser.add_argument("--skip-memory", action="store_true")
    parser.add_argument("--registry-only", action="store_true")
    parser.add_argument("--skip-registry", action="store_true")
    parser.add_argument("--samples", type=int)
    parser.add_argument("--cpu-samples", type=int)
    parser.add_argument(
        "--redis-url", help="Dedicated benchmark primary; only owned random prefixes are removed"
    )
    args = parser.parse_args()
    legacy = "engine" not in inspect.signature(NavigationConfig).parameters
    if legacy and args.engine == "rust":
        parser.error(
            "The published baseline does not implement Rust; no engine fallback is measured"
        )
    ages = args.ages or ([16] if legacy else [50, 500, 5000])
    sizes = args.registry_sizes or ([16] if legacy else [50, 500, 5000])
    samples = args.samples if args.samples is not None else (100 if args.quick or legacy else 1000)
    repeats = args.cpu_samples if args.cpu_samples is not None else (1 if args.quick else 10)
    if (
        min([samples, repeats, *ages, *sizes]) < 1
        or max(ages + sizes) > 10000
        or repeats > 100
        or samples > 10000
    ):
        parser.error("Benchmark dimensions exceed their bounded positive range")
    if args.registry_only and args.skip_registry:
        parser.error("--registry-only cannot be combined with --skip-registry")
    if args.skip_memory and args.skip_registry and not args.redis_url:
        parser.error("Select at least one CPU or Redis workload")
    results = []
    if not args.skip_memory and not args.registry_only:
        results.extend([await workload(age, args.engine, samples, repeats) for age in ages])
    if not args.skip_registry:
        results.extend(
            registry_workload(size, args.engine, 3 if args.quick else 10, repeats) for size in sizes
        )
    if args.redis_url and not args.registry_only:
        from redis_workload import workload as redis_workload

        for age in ages:
            results.extend(
                await redis_workload(args.redis_url, args.engine, age, samples, configuration)
            )
    try:
        commit = (
            await asyncio.to_thread(
                subprocess.check_output,
                ["git", "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = None
    report = dict(
        package="aiogram-nav",
        installed_version=version("aiogram-nav"),
        package_version=version("aiogram-nav"),
        controller_commit=commit,
        commit=None,
        driver_manifest={
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path(__file__).parent.glob("*.py")
        },
        engine=args.engine,
        python=sys.version,
        os=platform.platform(),
        cpu=platform.processor(),
        rust=await asyncio.to_thread(subprocess.getoutput, "rustc --version"),
        seed=0,
        warmup="fixture construction outside measured updates",
        qualification=False,
        qualification_owner="external serial comparison gate",
        exploratory=args.quick,
        representative_workload="memory-track/50",
        cpu_count=os.cpu_count(),
        rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        results=results,
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
