from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

SPEC = spec_from_file_location(
    "benchmark_controller", Path(__file__).parents[1] / "run_benchmarks.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_helper_changes_and_additions_change_fingerprint(tmp_path):
    (tmp_path / "run.py").write_text("pass\n")
    nested = tmp_path / "helpers"
    nested.mkdir()
    helper = nested / "wire.py"
    helper.write_text("VERSION = 1\n")
    before = MODULE.driver_fingerprints(tmp_path)
    assert set(before) == {"run.py", "helpers/wire.py"}
    helper.write_text("VERSION = 2\n")
    changed = MODULE.driver_fingerprints(tmp_path)
    assert changed != before
    assert changed["run.py"] == before["run.py"]
    (tmp_path / "extra.py").write_text("pass\n")
    assert MODULE.driver_fingerprints(tmp_path) != changed


def test_generated_non_source_files_do_not_change_fingerprint(tmp_path):
    (tmp_path / "run.py").write_text("pass\n")
    before = MODULE.driver_fingerprints(tmp_path)
    (tmp_path / "result.json").write_text("{}")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.py").write_text("pass\n")
    assert MODULE.driver_fingerprints(tmp_path) == before


def test_benchmark_bootstrap_uses_same_isolation_as_probe(tmp_path):
    import json
    import os
    import subprocess
    import sys

    probe = json.loads(
        subprocess.check_output([sys.executable, "-I", "-c", MODULE.PROBE, "pytest"], text=True)
    )
    # Both normal script-directory precedence and PYTHONPATH must lose to the
    # verified installed module preimport. Local benchmark helpers still work.
    (tmp_path / "pytest.py").write_text("raise RuntimeError('source shadow')\n")
    (tmp_path / "local_helper.py").write_text("VALUE = 42\n")
    driver = tmp_path / "run.py"
    driver.write_text(
        "import json,sys,pytest,local_helper\n"
        "print(json.dumps({'module':pytest.__file__,'helper':local_helper.VALUE,'argv':sys.argv[1:]}))\n"
    )
    output = tmp_path / "result.json"
    command = MODULE.benchmark_command(
        sys.executable, [probe], driver, "python", output, ["--samples", "3"]
    )
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    result = json.loads(subprocess.check_output(command, env=env, cwd=tmp_path, text=True))
    assert result["module"] == probe["module"]
    assert result["helper"] == 42
    assert result["argv"] == ["--engine", "python", "--output", str(output), "--samples", "3"]


def test_reserved_driver_flags_cannot_override_profile(tmp_path):
    import pytest

    for extra in [
        ["--engine", "rust"],
        ["--engine=rust"],
        ["--output=/tmp/other.json"],
        ["--eng=rust"],
        ["--out=other"],
    ]:
        with pytest.raises(ValueError, match="cannot override"):
            MODULE.benchmark_command("python", [], tmp_path / "run.py", "python", "out", extra)
