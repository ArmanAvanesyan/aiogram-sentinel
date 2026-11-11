"""Qualification must fail closed for regressions or incomparable evidence."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "comparison", Path(__file__).parents[1] / "compare_results.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def runs(engine, ratio=1):
    return [
        {
            "identity": ("package", "1.0", "3.12", "os", "cpu", 8, 137),
            "engine": engine,
            "path": f"{engine}-{index}",
            "sha256": hashlib.sha256(f"{engine}-{index}".encode()).hexdigest(),
            "run_id": f"{engine}-run-{index}",
            "qualification_provenance": {
                "base_artifact_sha256": "a" * 64,
                "native_artifact_sha256": "b" * 64 if engine == "rust" else None,
                "driver_sha256": "c" * 64,
            },
            "rows": {
                "core": {
                    "cpu_ns": 100 * ratio,
                    "cpu_samples": 15,
                    "p95_ns": 0,
                    "latency_samples": 0,
                    "calls": 1000,
                },
                "pipeline": {
                    "cpu_ns": 100,
                    "cpu_samples": 15,
                    "p95_ns": 100,
                    "latency_samples": 1000,
                    "calls": 1000,
                },
            },
        }
        for index in range(2)
    ]


def test_verified_benefit_qualifies():
    assert module.compare(runs("python"), runs("rust", 0.75), ["core"])["qualified"]


def test_insufficient_cpu_gain_is_withheld():
    result = module.compare(runs("python"), runs("rust", 0.90), ["core"])
    assert not result["qualified"] and any("below 20%" in item for item in result["failures"])


def test_batch_results_do_not_replace_operation_latencies():
    b = runs("rust", 0.7)
    for item in b:
        item["rows"]["pipeline"]["latency_samples"] = 0
    assert not module.compare(runs("python"), b, ["core"])["qualified"]


def test_p95_regression_blocks_even_fast_core():
    b = runs("rust", 0.5)
    for item in b:
        item["rows"]["pipeline"]["p95_ns"] = 120
    assert not module.compare(runs("python"), b, ["core"])["qualified"]


def test_noisy_repeats_are_not_qualified():
    b = runs("rust", 0.5)
    b[1]["rows"]["core"]["cpu_ns"] = 70
    assert not module.compare(runs("python"), b, ["core"])["qualified"]


def test_different_runtime_or_counts_are_not_compared():
    a, b = runs("python"), runs("rust", 0.7)
    different = deepcopy(b)
    different[0]["identity"] = ("wrong",)
    with pytest.raises(ValueError, match="not matched"):
        module.compare(a, different, ["core"])
    b[0]["rows"]["core"]["calls"] = 2000
    assert not module.compare(a, b, ["core"])["qualified"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0])
@pytest.mark.parametrize("field,name", [("cpu_ns", "core"), ("p95_ns", "pipeline")])
def test_non_finite_or_non_positive_evidence_cannot_qualify(value, field, name):
    b = runs("rust", 0.5)
    b[0]["rows"][name][field] = value
    assert not module.compare(runs("python"), b, ["core"])["qualified"]


def test_cpu_workload_cannot_be_omitted():
    with pytest.raises(ValueError, match="representative CPU"):
        module.compare(runs("python"), runs("rust", 0.5), [])


@pytest.mark.parametrize("field", ["calls", "cpu_samples", "latency_samples"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, 0, -1, 1000.0, "1000"])
def test_counts_require_positive_integers(field, value):
    b = runs("rust", 0.5)
    name = "pipeline" if field == "latency_samples" else "core"
    b[0]["rows"][name][field] = value
    assert not module.compare(runs("python"), b, ["core"])["qualified"]


@pytest.mark.parametrize("field", ["path", "sha256", "run_id"])
@pytest.mark.parametrize("across_engines", [False, True])
def test_duplicate_input_identity_cannot_qualify(field, across_engines):
    a, b = runs("python"), runs("rust", 0.5)
    b[1][field] = a[0][field] if across_engines else b[0][field]
    assert not module.compare(a, b, ["core"])["qualified"]


@pytest.mark.parametrize(
    "field", ["base_artifact_sha256", "native_artifact_sha256", "driver_sha256"]
)
@pytest.mark.parametrize("value", [None, "", "wrong", "f" * 64])
def test_missing_invalid_or_mismatched_provenance_cannot_qualify(field, value):
    b = runs("rust", 0.5)
    b[0]["qualification_provenance"][field] = value
    assert not module.compare(runs("python"), b, ["core"])["qualified"]


def test_python_cannot_claim_native_provenance():
    a = runs("python")
    a[0]["qualification_provenance"]["native_artifact_sha256"] = "b" * 64
    assert not module.compare(a, runs("rust", 0.5), ["core"])["qualified"]


def test_historical_missing_provenance_fails_qualification_without_raising():
    a = runs("python")
    for item in a:
        item.pop("qualification_provenance")
    result = module.compare(a, runs("rust", 0.5), ["core"])
    assert not result["qualified"]
    assert any("provenance" in failure for failure in result["failures"])


def test_load_preserves_top_level_qualification_provenance(tmp_path):
    item = runs("python")[0]
    document = {
        "metadata": dict(
            zip(
                ("package", "version", "python", "os", "cpu", "cpu_count", "seed"),
                item["identity"],
                strict=True,
            ),
            engine="python",
        ),
        "run_id": item["run_id"],
        "qualification_provenance": item["qualification_provenance"],
        "benchmarks": {"core": {"cpu_ns": {"median": 100}, "samples": 15, "loops": 1000}},
    }
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(document))
    loaded = module.load(path)
    assert loaded["run_id"] == item["run_id"]
    assert loaded["qualification_provenance"] == item["qualification_provenance"]
    document.pop("qualification_provenance")
    document.pop("run_id")
    path.write_text(json.dumps(document))
    historical = module.load(path)
    assert historical["qualification_provenance"] is None
    assert historical["run_id"] is None
