"""Portable installed-distribution benchmark controller; qualification is external."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
from importlib.metadata import distribution, version
from pathlib import Path

from aiogram_idle import MemoryIdleBackend

if __package__:
    from .support import driver_manifest, provenance
    from .workloads import (
        admission_trajectory,
        claim_workload,
        combined_workload,
        configuration,
        loop_lag_workload,
        memory_workload,
        redis_workload,
    )
else:
    from support import driver_manifest, provenance
    from workloads import (
        admission_trajectory,
        claim_workload,
        combined_workload,
        configuration,
        loop_lag_workload,
        memory_workload,
        redis_workload,
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("python", "rust"), default="python")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--redis-url", default=os.environ.get("AIOGRAM_IDLE_REDIS_URL"))
    parser.add_argument("--ages", nargs="+", type=int)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--cpu-samples", type=int)
    parser.add_argument("--skip-redis", action="store_true")
    parser.add_argument(
        "--combined",
        action="store_true",
        help="Include optional navigation integration diagnostics",
    )
    parser.add_argument("--skip-combined", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-admission", action="store_true")
    parser.add_argument(
        "--allow-editable",
        action="store_true",
        help="Exploratory smoke only; final qualification uses installed wheels",
    )
    args = parser.parse_args()
    # Reject unsupported engine requests before creating a backend or namespace.
    configuration(args.engine)
    if args.combined and not args.skip_combined:
        # Validate optional engine availability before any namespace initialization.
        from aiogram_nav import NavigationRegistry, Node

        registry_kwargs = {
            "nodes": [Node("main", renderer="app")],
            "roots": {"main"},
        }
        if "engine" in inspect.signature(NavigationRegistry).parameters:
            registry_kwargs["engine"] = args.engine
        elif args.engine != "python":
            parser.error("This installed Nav version does not support engine selection")
        NavigationRegistry(**registry_kwargs)
    direct = distribution("aiogram-idle").read_text("direct_url.json")
    if (
        direct
        and json.loads(direct).get("dir_info", {}).get("editable")
        and not args.allow_editable
    ):
        parser.error(
            "This environment uses editable Idle; install its wheel or explicitly select --allow-editable for exploratory smoke"
        )
    ages = args.ages or ([1, 10, 50] if args.quick else [1, 10, 50, 500, 5000])
    samples = args.samples or (8 if args.quick else 100)
    repeats = args.cpu_samples or (1 if args.quick else 10)
    if any(value < 1 for value in [*ages, samples, repeats]):
        parser.error("ages/samples/cpu-samples must be positive")
    rows = []
    for age in ages:
        rows.append(await memory_workload(age, args.engine, samples, repeats))
    rows.append(await claim_workload(args.engine, samples, repeats))
    rows.append(await loop_lag_workload(args.engine, samples))
    if args.redis_url and not args.skip_redis and args.combined and not args.skip_combined:
        if __package__:
            from .dispatcher import workload as dispatcher_workload
        else:
            from dispatcher import workload as dispatcher_workload
        rows.append(await dispatcher_workload(args.redis_url, args.engine, samples))
    if not args.skip_admission:
        rows.extend(await admission_trajectory(args.engine, ages))
        rows.extend(await admission_trajectory(args.engine, ages, short_replay=True))
    for age in ages:
        if args.redis_url and not args.skip_redis:
            rows.append(await redis_workload(args.redis_url, age, args.engine, samples))
        if args.combined and not args.skip_combined:
            # Published combined snapshots grow quadratically; default-capacity
            # failure is reported separately, not hidden by an enormous legacy cap.
            legacy = "storage_format" not in inspect.signature(MemoryIdleBackend).parameters
            if legacy and age > 50:
                rows.append(
                    {
                        "scenario": "combined-legacy-age",
                        "workload": f"combined-legacy-age/{age}",
                        "state_age": age,
                        "unavailable": "Legacy high-capacity full-snapshot growth is unsafe; use default-admission trajectory as the bounded capacity evidence",
                        "qualification": False,
                    }
                )
                continue
            rows.append(await combined_workload(None, age, args.engine, samples))
            if args.redis_url and not args.skip_redis:
                rows.append(await combined_workload(args.redis_url, age, args.engine, samples))
    report = {
        **provenance(),
        "engine": args.engine,
        "qualification": False,
        "qualification_owner": "external serial comparison gate; two serial runs per engine",
        "representative_workload": "memory-activate-touch/50",
        "exploratory": args.quick or args.allow_editable,
        "driver_manifest": driver_manifest(),
        "commit": None,
        "cpu_count": os.cpu_count(),
        "samples": samples,
        "cpu_samples": repeats,
        "results": rows,
        "dependencies": {name: version(name) for name in ("aiogram", "aiogram-coordination")},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
