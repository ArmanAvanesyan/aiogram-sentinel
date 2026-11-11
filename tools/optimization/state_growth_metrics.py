"""Benchmark instrumentation; no library implementation imports."""

import asyncio
import math
from collections import Counter
from contextlib import contextmanager
from dataclasses import fields, is_dataclass


class CommandMetrics:
    """Compute RESP2 request framing for client-supplied commands only."""

    def __init__(self):
        self.enabled = True
        self.calls = self.pipeline_batches = self.argument_bytes = self.resp_bytes = 0
        self.commands = Counter()

    def observe(self, args, encoder=None, *, invocation=True):
        if not self.enabled:
            return
        values = list(args)
        if values and isinstance(values[0], (str, bytes)):
            first = values.pop(0)
            first = first.encode() if isinstance(first, str) else first
            values = [*first.split(), *values]
        encoded = [
            encoder.encode(value)
            if encoder
            else (value if isinstance(value, bytes) else str(value).encode())
            for value in values
        ]
        self.calls += int(invocation)
        self.commands[encoded[0].decode(errors="replace").upper() if encoded else "EMPTY"] += 1
        self.argument_bytes += sum(len(value) for value in encoded)
        self.resp_bytes += len(f"*{len(encoded)}\r\n".encode()) + sum(
            len(f"${len(value)}\r\n".encode()) + len(value) + 2 for value in encoded
        )

    @contextmanager
    def paused(self):
        old, self.enabled = self.enabled, False
        try:
            yield
        finally:
            self.enabled = old

    def snapshot(self):
        return {
            "client_command_calls": self.calls,
            "pipeline_execute_calls": self.pipeline_batches,
            "command_argument_bytes": self.argument_bytes,
            "computed_resp_request_bytes": self.resp_bytes,
            "command_histogram": dict(self.commands),
        }


def counting_redis(url, metrics):
    from redis.asyncio import Redis

    class CountingRedis(Redis):
        async def execute_command(self, *args, **options):
            metrics.observe(args, self.get_encoder())
            return await super().execute_command(*args, **options)

        def pipeline(self, transaction=True, shard_hint=None):
            pipe = super().pipeline(transaction=transaction, shard_hint=shard_hint)
            original = pipe.execute

            async def execute(*args, **kwargs):
                if metrics.enabled:
                    metrics.pipeline_batches += 1
                    if transaction:
                        metrics.observe(("MULTI",), invocation=False)
                    for command, _ in pipe.command_stack:
                        metrics.observe(command, self.get_encoder(), invocation=False)
                    if transaction:
                        metrics.observe(("EXEC",), invocation=False)
                return await original(*args, **kwargs)

            pipe.execute = execute
            return pipe

    return CountingRedis.from_url(url)


class LagProbe:
    def __init__(self, interval=0.005):
        self.interval, self.values, self.maximum, self.count = interval, [], 0.0, 0
        self.generation = 0

    async def run(self):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.interval
        while True:
            generation = self.generation
            await asyncio.sleep(max(0.0, deadline - loop.time()))
            if generation != self.generation:
                deadline = loop.time() + self.interval
                continue
            delay = max(0.0, loop.time() - deadline)
            self.maximum, self.count = max(self.maximum, delay), self.count + 1
            if len(self.values) < 100000:
                self.values.append(delay)
            deadline = loop.time() + self.interval

    def report(self):
        values = sorted(self.values)
        return {
            "samples": self.count,
            "retained_samples": len(values),
            "maximum_seconds": self.maximum,
            "p95_seconds": values[min(len(values) - 1, math.ceil(len(values) * 0.95) - 1)]
            if values
            else None,
            "interval_seconds": self.interval,
        }


def plain(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def classify_redis_key(key, prefix):
    """Classify this run's own keys using reviewed Redis key conventions."""
    suffix = key.decode().removeprefix(prefix + ":")
    if suffix.startswith("record:") and len(suffix.split(":")) == 2:
        return "hot"
    if suffix.startswith("receipt:") or ":operation:" in suffix:
        return "cold_receipt"
    if suffix.startswith("result:"):
        return "cold_result"
    return "other"


async def redis_state(client, prefix):
    result = {
        "redis_keys": 0,
        "redis_string_payload_bytes": 0,
        "redis_memory_usage_bytes": 0,
        "redis_record_string_bytes": 0,
        "redis_hot_string_bytes": 0,
        "redis_cold_receipt_count": 0,
        "redis_cold_receipt_string_bytes": 0,
        "redis_cold_result_string_bytes": 0,
    }
    async for key in client.scan_iter(match=prefix + ":*", count=100):
        result["redis_keys"] += 1
        result["redis_memory_usage_bytes"] += await client.memory_usage(key) or 0
        kind = classify_redis_key(key, prefix)
        if kind == "cold_receipt":
            result["redis_cold_receipt_count"] += 1
        if await client.type(key) == b"string":
            size = await client.strlen(key)
            result["redis_string_payload_bytes"] += size
            if b":record:" in key:
                result["redis_record_string_bytes"] += size
            if kind in {"hot", "cold_receipt", "cold_result"}:
                result[f"redis_{kind}_string_bytes"] += size
    return result
