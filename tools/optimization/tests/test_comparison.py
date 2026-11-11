"""Qualification must fail closed for regressions or incomparable evidence."""

import importlib.util
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
            "sha256": "test",
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
