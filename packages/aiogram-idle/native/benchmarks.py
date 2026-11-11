"""Labelled microbenchmarks, not a substitute for serialized end-to-end qualification.

Uses the installed base package; no source-path injection. The Python engine is
its deterministic reference implementation. The root benchmark driver separately
compares the published 0.2 baseline, optimized Python and native full workflows.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import socket
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from aiogram_idle.engines import fingerprint_canonical, make_queue, phase_transition, require_engine
from aiogram_idle.models import (
    IdleConversationKey,
    IdleSnapshot,
    Phase,
    RuntimeSnapshot,
    SessionSnapshot,
)


def workloads(engine):
    keys = [IdleConversationKey("benchmark", 1, index, index) for index in range(1, 513)]
    records = [
        RuntimeSnapshot(
            key, SessionSnapshot("session", 1000), idle=IdleSnapshot(phase=Phase.ACTIVE, deadline=1)
        )
        for key in keys
    ]
    raw = json.dumps(
        {"draft": "fixed-payload" * 200, "flow": "form", "revision": 2},
        sort_keys=True,
        separators=(",", ":"),
    )

    def lifecycle():
        for _ in range(1000):
            assert phase_transition("prompted", "continue", engine=engine) == "resuming"
            assert phase_transition("resuming", "finish", engine=engine) == "active"

    def fingerprint():
        for _ in range(1000):
            fingerprint_canonical(raw, engine=engine)

    def queue():
        pending = make_queue(engine)
        for record in records:
            pending.schedule(record)
        claims = pending.claim(limit=512, lease_seconds=60, now=2)
        for claim in claims:
            pending.renew(claim, now=3, lease_seconds=60)
            pending.release(claim, records[claim.key.chat_id - 1], now=4, retry_at=10)
        assert len(pending.jobs) == 512

    return {
        "lifecycle_2000": lifecycle,
        "exact_sha256_1000_fixed_2kb": fingerprint,
        "queue_512_schedule_claim_renew_release": queue,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("python", "rust"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--host-label", default=socket.gethostname())
    args = parser.parse_args()
    require_engine(args.engine)
    measured = {}
    # Caller-provided deterministic tokens isolate algorithm CPU from OS entropy.
    with patch("secrets.token_urlsafe", return_value="benchmark-token"):
        for name, action in workloads(args.engine).items():
            for _ in range(2):
                action()
            cpu, elapsed = [], []
            enabled = gc.isenabled()
            gc.disable()
            try:
                for _ in range(5 if args.quick else 30):
                    start, cpu_start = time.perf_counter_ns(), time.process_time_ns()
                    action()
                    cpu.append(time.process_time_ns() - cpu_start)
                    elapsed.append(time.perf_counter_ns() - start)
            finally:
                if enabled:
                    gc.enable()
            measured[name] = {
                "samples": len(cpu),
                "cpu_median_ns": statistics.median(cpu),
                "elapsed_median_ns": statistics.median(elapsed),
                "elapsed_p95_ns": statistics.quantiles(elapsed, n=20, method="inclusive")[18],
            }
    result = {
        "schema": 1,
        "kind": "microbenchmark_not_end_to_end",
        "engine": args.engine,
        "host_label": args.host_label,
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "at": datetime.now(timezone.utc).isoformat(),
        "warmup_batches": 2,
        "entropy": "caller-provided deterministic tokens",
        "results": measured,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
