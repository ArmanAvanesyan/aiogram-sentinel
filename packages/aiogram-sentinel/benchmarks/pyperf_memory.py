"""pyperf calibrated measurements of installed public memory operations.

SENTINEL_ENGINE=rust python benchmarks/pyperf_memory.py -o results.json
The published 1.2 baseline accepts SENTINEL_ENGINE=python only.
"""

import asyncio
import inspect
import os

import pyperf

from aiogram_sentinel.storage.memory import MemoryDebounce, MemoryRateLimiter

engine = os.environ.get("SENTINEL_ENGINE", "python")
options = (
    {"engine": engine}
    if "engine" in inspect.signature(MemoryRateLimiter).parameters
    else {}
)
if engine == "rust" and not options:
    raise RuntimeError("Published baseline does not support Rust")
rate = MemoryRateLimiter(**options)
debounce = MemoryDebounce(**options)
loop = asyncio.new_event_loop()
loop.run_until_complete(rate.allow("hot", 1, 3600))
loop.run_until_complete(debounce.seen("hot", 3600, "fp"))


async def calls(kind):
    for _ in range(1000):
        if kind == "rate":
            await rate.allow("hot", 1, 3600)
        else:
            await debounce.seen("hot", 3600, "fp")


if __name__ == "__main__":
    runner = pyperf.Runner()
    runner.metadata["engine"] = engine
    runner.bench_func(
        "rate_rejected_hot_1000", lambda: loop.run_until_complete(calls("rate"))
    )
    runner.bench_func(
        "debounce_rejected_hot_1000", lambda: loop.run_until_complete(calls("debounce"))
    )
    loop.close()
