"""Evaluate explicit CPU and individual-latency gates from matched runs.

This is a local evidence evaluator, not a publisher. Select representative CPU
workloads before running benchmarks; do not select a winning subset afterward.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
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
        "run_id": document.get("run_id", metadata.get("run_id")),
        "qualification_provenance": document.get("qualification_provenance"),
        "rows": rows,
    }


def positive_integer(value: object) -> bool:
    return type(value) is int and value > 0


def positive_finite(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def provenance_failures(runs: list[dict]) -> list[str]:
    failures = []
    for field in ("sha256", "path", "run_id"):
        values = [item.get(field) for item in runs]
        if any(not isinstance(value, str) or not value for value in values):
            failures.append(f"Missing input identity: {field}")
        elif len(set(values)) != len(values):
            failures.append(f"Duplicate input identity: {field}")
    if any(not digest(item.get("sha256")) for item in runs):
        failures.append("Invalid input checksum")
    proven = []
    for item in runs:
        value = item.get("qualification_provenance")
        if (
            not isinstance(value, dict)
            or set(value) != {"base_artifact_sha256", "native_artifact_sha256", "driver_sha256"}
            or not digest(value.get("base_artifact_sha256"))
            or not digest(value.get("driver_sha256"))
            or (item["engine"] == "python" and value.get("native_artifact_sha256") is not None)
            or (item["engine"] == "rust" and not digest(value.get("native_artifact_sha256")))
        ):
            failures.append(f"Missing or invalid qualification provenance: {item.get('path')}")
        else:
            proven.append((item["engine"], value))
    if len(proven) == len(runs):
        for field in ("base_artifact_sha256", "driver_sha256"):
            if len({value[field] for _, value in proven}) != 1:
                failures.append(f"Mismatched qualification provenance: {field}")
        if (
            len({value["native_artifact_sha256"] for engine, value in proven if engine == "rust"})
            != 1
        ):
            failures.append("Mismatched qualification provenance: native_artifact_sha256")
    return failures


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
    evidence, failures = [], provenance_failures(all_runs)
    for item in all_runs:
        for name, row in item["rows"].items():
            if (
                not positive_integer(row["calls"])
                or not positive_integer(row["cpu_samples"])
                or not positive_finite(row["cpu_ns"])
            ):
                failures.append(f"Invalid CPU evidence or operation counts: {name}")
            count = row["latency_samples"]
            if not (type(count) is int and count == 0) and (
                not positive_integer(count) or not positive_finite(row["p95_ns"])
            ):
                failures.append(f"Invalid individual latency evidence: {name}")
    latency_names = {
        name
        for item in all_runs
        for name, row in item["rows"].items()
        if not (type(row["latency_samples"]) is int and row["latency_samples"] == 0)
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
        if any(not positive_integer(row["calls"]) for row in a + b):
            failures.append(f"Invalid operation counts: {name}")
            continue
        if len({row["calls"] for row in a + b}) != 1:
            failures.append(f"Different operation counts: {name}")
            continue
        row: dict[str, object] = {"workload": name}
        if name in workloads:
            if any(
                not positive_integer(item["cpu_samples"])
                or item["cpu_samples"] < 10
                or not positive_finite(item["cpu_ns"])
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
                not positive_integer(item["latency_samples"])
                or item["latency_samples"] < 100
                or not positive_finite(item["p95_ns"])
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
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "engine": item["engine"],
                "run_id": item.get("run_id"),
                "qualification_provenance": item.get("qualification_provenance"),
            }
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
