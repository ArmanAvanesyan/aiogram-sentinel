"""Evaluate explicit CPU and individual-latency gates from matched runs.

This is a local evidence evaluator, not a publisher. Select representative CPU
workloads before running benchmarks; do not select a winning subset afterward.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path


def load(path: Path) -> dict:
    document = json.loads(path.read_text())
    metadata = document.get("metadata", document)
    rows = {}
    if isinstance(document.get("results"), list):
        for row in document["results"]:
            rows[row["workload"]] = {
                "cpu_ns": row["median_process_cpu_seconds"] * 1e9,
                "cpu_samples": len(row["process_cpu_seconds"]),
                "p95_ns": row.get("update_p95_seconds", 0) * 1e9,
                "latency_samples": row.get("update_sample_count", 0),
                "calls": row["calls"],
            }
    elif isinstance(document.get("benchmarks"), dict):
        for name, row in document["benchmarks"].items():
            individual = row.get("individual_latency_ns", {})
            rows[name] = {
                "cpu_ns": row["cpu_ns"]["median"],
                "cpu_samples": row["samples"],
                "p95_ns": individual.get("p95") or 0,
                "latency_samples": individual.get("count", 0),
                "calls": row["loops"],
            }
    else:
        raise TypeError(f"Benchmark result collection is missing: {path}")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "identity": (
            metadata["package"],
            metadata.get("package_version", metadata.get("version")),
            metadata["python"],
            metadata["os"],
            metadata["cpu"],
            metadata["cpu_count"],
            metadata["seed"],
        ),
        "engine": metadata["engine"],
        "rows": rows,
    }


def compare(python: list[dict], rust: list[dict], workloads: list[str]) -> dict:
    if not workloads:
        raise ValueError("At least one representative CPU workload is required")
    if len(python) < 2 or len(rust) < 2:
        raise ValueError("At least two independent runs per engine are required")
    all_runs = python + rust
    if len({item["identity"] for item in all_runs}) != 1:
        raise ValueError("Package/version/Python/host/seed differ; comparison is not matched")
    if any(item["engine"] != "python" for item in python) or any(
        item["engine"] != "rust" for item in rust
    ):
        raise ValueError("Input engine selection does not match the requested groups")
    evidence, failures = [], []
    latency_names = {
        name
        for item in all_runs
        for name, row in item["rows"].items()
        if row["latency_samples"] > 0
    }
    if not latency_names:
        failures.append("No individual end-to-end operation latency samples")
    for name in sorted(set(workloads) | latency_names):
        try:
            a, b = (
                [item["rows"][name] for item in python],
                [item["rows"][name] for item in rust],
            )
        except KeyError:
            failures.append(f"Missing comparable workload: {name}")
            continue
        if len({row["calls"] for row in a + b}) != 1:
            failures.append(f"Different operation counts: {name}")
            continue
        row: dict[str, object] = {"workload": name}
        if name in workloads:
            if any(
                item["cpu_samples"] < 10 or not math.isfinite(item["cpu_ns"]) or item["cpu_ns"] <= 0
                for item in a + b
            ):
                failures.append(f"Insufficient CPU samples: {name}")
            else:
                ratio = statistics.median(item["cpu_ns"] for item in b) / statistics.median(
                    item["cpu_ns"] for item in a
                )
                row["rust_over_python_cpu"] = ratio
                if ratio > 0.8:
                    failures.append(f"CPU improvement below 20%: {name}")
                if any(
                    max(item["cpu_ns"] for item in group) / min(item["cpu_ns"] for item in group)
                    > 1.10
                    for group in (a, b)
                ):
                    failures.append(f"CPU repeat spread exceeds 10%: {name}")
        if name in latency_names:
            if any(
                item["latency_samples"] < 100
                or not math.isfinite(item["p95_ns"])
                or item["p95_ns"] <= 0
                for item in a + b
            ):
                failures.append(f"Insufficient individual latency samples: {name}")
            else:
                ratio = statistics.median(item["p95_ns"] for item in b) / statistics.median(
                    item["p95_ns"] for item in a
                )
                row["rust_over_python_p95"] = ratio
                if ratio > 1.05:
                    failures.append(f"End-to-end p95 regression exceeds 5%: {name}")
                if any(
                    max(item["p95_ns"] for item in group) / min(item["p95_ns"] for item in group)
                    > 1.10
                    for group in (a, b)
                ):
                    failures.append(f"Latency repeat spread exceeds 10%: {name}")
        evidence.append(row)
    return {
        "schema_version": 1,
        "qualified": not failures,
        "identity": all_runs[0]["identity"],
        "cpu_workloads_selected": workloads,
        "inputs": [
            {"path": item["path"], "sha256": item["sha256"], "engine": item["engine"]}
            for item in all_runs
        ],
        "comparisons": evidence,
        "failures": failures,
        "scope": "Measured host/workloads only; functional platform CI and independent review remain separate release gates.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", action="append", required=True, type=Path)
    parser.add_argument("--rust", action="append", required=True, type=Path)
    parser.add_argument("--cpu-workload", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = compare(
        [load(path) for path in args.python],
        [load(path) for path in args.rust],
        args.cpu_workload,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
