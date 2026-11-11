"""Render measured storage trajectories and native CPU gates; no extrapolation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def collect(reports):
    growth = reports / "optimization" / "state-growth"
    inputs = [
        growth / "baseline-20261111" / "combined-redis.json",
        growth / "candidate-idle-030" / "combined-redis-default.json",
        growth / "candidate-idle-030" / "combined-redis-stress.json",
    ]
    baseline, default, stress = [load(path)["checkpoints"] for path in inputs]
    candidates = {row["operations"]: row for row in [*default, *stress]}
    program = reports / "2026-11-11-optimization-program"
    native = []
    for name in ("sentinel", "cmds", "nav", "idle"):
        path = program / (name + "-serial") / "native-gate.json"
        inputs.append(path)
        data = load(path)
        for row in data["comparisons"]:
            if "rust_over_python_cpu" in row:
                native.append(
                    {
                        "package": data["identity"][0],
                        "workload": row["workload"],
                        "ratio": row["rust_over_python_cpu"],
                        "qualified": data["qualified"],
                    }
                )
    return {
        "baseline": baseline,
        "candidate": [candidates[count] for count in sorted(candidates)],
        "native": native,
        "inputs": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
        "notes": [
            "Measured points only; baseline ended at16. No extrapolated old5000 value.",
            "Candidate5000 explicitly uses10000 receipt slots; default remains256.",
            "Hot state excludes separately retained cold receipts; total JSON includes both.",
            "Native CPU ratios are candidate measurements, not production speed claims.",
        ],
    }


def save_figure(figure, path, extension):
    metadata = {"Date": None} if extension == "svg" else None
    figure.savefig(path, dpi=160, metadata=metadata)
    if extension == "svg":
        path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")


def draw(data, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.hashsalt": "aiogram-optimization-20261111",
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), constrained_layout=True)
    for axis, field, title in zip(
        axes,
        ("redis_record_string_bytes", "redis_string_payload_bytes"),
        ("Hot conversation JSON", "Total retained JSON (hot + cold)"),
        strict=True,
    ):
        for label, rows, color in (
            ("Published 0.2 combined", data["baseline"], "#9b2226"),
            ("Candidate 0.3 combined", data["candidate"], "#2d6a4f"),
        ):
            axis.loglog(
                [row["operations"] for row in rows],
                [row[field] / 1024 for row in rows],
                "o-",
                color=color,
                label=label,
            )
        axis.set(title=title, xlabel="Accepted navigation operations", ylabel="KiB")
        axis.grid(True, which="major", alpha=0.25)
        axis.legend(fontsize=8)
    fig.suptitle("Redis storage: bounded hot state, linear retained evidence", fontsize=13)
    fig.supxlabel(
        "Fixed inputs, history capped at 20. Stress capacity 10,000; default 256. Measured points only.",
        fontsize=9,
    )
    for extension in ("png", "svg"):
        save_figure(fig, output / ("state-growth." + extension), extension)
    plt.close(fig)

    labels = []
    for row in data["native"]:
        name = row["package"].removeprefix("aiogram-").title()
        suffix = (
            "debounce" if "debounce" in row["workload"] else "rate" if name == "Sentinel" else ""
        )
        labels.append(name + (": " + suffix if suffix else ""))
    ratios = [row["ratio"] for row in data["native"]]
    fig, axis = plt.subplots(figsize=(9, 4.6), constrained_layout=True)
    bars = axis.barh(
        labels, ratios, color=["#b88722" if value < 1 else "#a63d40" for value in ratios]
    )
    axis.axvline(0.8, color="#2d6a4f", linestyle="--", label="CPU gate: ratio ≤ 0.8")
    axis.axvline(1, color="#555555", linewidth=0.8)
    axis.bar_label(bars, fmt="%.3f", padding=5)
    axis.invert_yaxis()
    axis.set(
        xlabel="Rust CPU / optimized Python CPU (lower is better)", xlim=(0, max(ratios) * 1.18)
    )
    axis.set_title("Native publication withheld in all four libraries", fontsize=13)
    axis.legend(loc="lower right")
    fig.supxlabel(
        "Candidate workloads on the recorded host. Passing CPU alone would not satisfy latency and artifact gates.",
        fontsize=9,
    )
    for extension in ("png", "svg"):
        save_figure(fig, output / ("native-gates." + extension), extension)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=Path(__file__).parents[2] / "reports")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = collect(args.reports)
    (args.output / "chart-data.json").write_text(json.dumps(data, indent=2) + "\n")
    draw(data, args.output)


if __name__ == "__main__":
    main()
