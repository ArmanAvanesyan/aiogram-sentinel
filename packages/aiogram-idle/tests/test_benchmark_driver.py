"""The portable driver reports raw evidence without self-qualifying."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from benchmarks.support import command_summary, measured_row, percentile, provenance
from benchmarks.workloads import memory_workload


def test_nearest_rank_p95_and_raw_cpu_samples():
    row = measured_row("example", 50, "python", 100, [0.1] * 10, list(range(100)))
    assert row["process_cpu_seconds"] == [0.1] * 10
    assert row["cpu_count"] == 10
    assert row["update_sample_count"] == 100
    assert row["update_p95_seconds"] == 94
    assert percentile([]) is None


def test_network_counts_do_not_claim_lua_cpu():
    summary = command_summary(
        [
            {"command": "EVALSHA", "argument_bytes": 10, "elapsed_seconds": 0.1},
            {"command": "GET", "argument_bytes": 2, "elapsed_seconds": 0.01},
        ]
    )
    assert summary["client_round_trips"] == 2
    assert summary["lua_calls"] == 1
    assert summary["direct_commands"] == 1
    assert summary["argument_payload_bytes"] == 12
    assert summary["lua_server_cpu_seconds"] is None


def test_representative_memory_workload_uses_raw_samples():
    row = asyncio.run(memory_workload(1, "python", 3, 2))
    assert row["calls"] == 3
    assert len(row["process_cpu_seconds"]) == 2
    assert len(row["raw_latency_seconds"]) == 6
    assert row["client_round_trips"] == 0
    assert row["application_authority_calls"] > 0


def test_provenance_comes_from_installed_distribution():
    report = provenance()
    assert report["package"] == "aiogram-idle"
    assert report["module_file"]
    assert report["installed_version"]


def test_controller_never_modifies_import_search_path():
    directory = Path(__file__).parents[1] / "benchmarks"
    for source in directory.glob("*.py"):
        assert "sys.path." not in source.read_text()


def test_standalone_controller_does_not_import_nav(tmp_path):
    # Inspect imported modules in a fresh interpreter after executing the actual
    # controller's ordinary path. The optional distribution may be installed.
    output = tmp_path / "benchmark.json"
    driver = Path(__file__).parents[1] / "benchmarks" / "run.py"
    script = (
        "import runpy,sys; "
        f'sys.argv=[{str(driver)!r},"--output",{str(output)!r},"--quick","--ages","1",'
        '"--samples","2","--skip-admission","--allow-editable"]; '
        # run_path doesn't add its directory like Python script execution does;
        # use the package route without any import path modification instead.
        'runpy.run_module("benchmarks.run",run_name="__main__"); '
        'assert not any(n=="aiogram_nav" or n.startswith("aiogram_nav.") for n in sys.modules)'
    )
    subprocess.run([sys.executable, "-c", script], check=True)
    report = json.loads(output.read_text())
    assert report["qualification"] is False
    assert report["representative_workload"] == "memory-activate-touch/50"
