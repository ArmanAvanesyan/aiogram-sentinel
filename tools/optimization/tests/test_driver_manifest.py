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
