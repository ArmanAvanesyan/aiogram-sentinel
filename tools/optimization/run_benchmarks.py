"""Run repository benchmarks using explicitly installed distributions.

The benchmark drivers live in their owning repositories. Run each profile in a
separate fresh environment; this controller never installs or rebuilds packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

PACKAGES = ("aiogram-sentinel", "aiogram-cmds", "aiogram-nav", "aiogram-idle")
PROBE_COMMON = """
import hashlib, importlib, importlib.metadata, json, sys
from pathlib import Path
MODULES = {
    'aiogram-sentinel-native': '_aiogram_sentinel_native',
    'aiogram-cmds-native': '_aiogram_cmds_native',
    'aiogram-nav-native': 'aiogram_nav_native',
    'aiogram-idle-native': 'aiogram_idle_native',
}
def installed(name):
    package = importlib.import_module(MODULES.get(name, name.replace('-', '_')))
    distribution = importlib.metadata.distribution(name)
    direct = json.loads(distribution.read_text('direct_url.json') or '{}')
    if direct.get('dir_info', {}).get('editable'):
        raise RuntimeError('Benchmark environment must install artifacts, not editable sources')
    if 'site-packages' not in str(package.__file__):
        raise RuntimeError('Checkout shadows the benchmark distribution')
    archive = direct.get('archive_info', {})
    digest = archive.get('hashes', {}).get('sha256')
    if not digest and archive.get('hash', '').startswith('sha256='):
        digest = archive['hash'].split('=', 1)[1]
    return {'distribution': name, 'version': distribution.version,
            'module': str(package.__file__), 'python': sys.version,
            'module_sha256': hashlib.sha256(Path(package.__file__).read_bytes()).hexdigest(),
            'artifact_sha256': digest,
            'executable': sys.executable, 'direct_url': direct}
"""
PROBE = PROBE_COMMON + "\nprint(json.dumps(installed(sys.argv[1])))\n"
BOOTSTRAP = (
    PROBE_COMMON
    + """
import runpy
expected = json.loads(sys.argv[1])
for probe in expected:
    if installed(probe['distribution']) != probe:
        raise RuntimeError('Actual benchmark imports differ from the isolated installed probe')
driver = Path(sys.argv[2])
sys.argv = [str(driver), *sys.argv[3:]]
# The verified installed packages are already imported before local helper paths.
# Their __path__ remains the installed package path, including lazy submodules.
sys.path.insert(0, str(driver.parent))
runpy.run_path(str(driver), run_name='__main__')
"""
)


def benchmark_command(executable, probes, driver, engine, result, extra, quick=False):
    for argument in extra:
        flag = argument.split("=", 1)[0]
        if flag.startswith("--") and any(
            reserved.startswith(flag) for reserved in ("--engine", "--output")
        ):
            raise ValueError("Driver arguments cannot override the verified engine or output")
    command = [
        str(executable),
        "-I",
        "-c",
        BOOTSTRAP,
        json.dumps(probes),
        str(driver),
        "--engine",
        engine,
        "--output",
        str(result),
    ]
    if quick:
        command.append("--quick")
    return command + list(extra)


def driver_fingerprints(directory: Path) -> dict[str, str]:
    """Freeze the driver and local helper modules, excluding generated caches."""
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--profile", required=True, choices=("baseline", "optimized", "native"))
    parser.add_argument("--package", action="append", choices=PACKAGES)
    parser.add_argument("--repositories", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--redis-url")
    parser.add_argument(
        "--driver-arg",
        action="append",
        default=[],
        help="Explicit benchmark driver argument; use --driver-arg=--flag for flags",
    )
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    # Resolving a venv's python symlink would select the global interpreter and
    # silently discard the installed profile this controller is meant to audit.
    executable = args.python.absolute()
    if not executable.is_file():
        parser.error(f"Python executable does not exist: {executable}")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "profile": args.profile,
        "started_at": time.time(),
        "machine": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "cpus": os.cpu_count(),
        },
        "quick": args.quick,
        "qualification": False,
        "note": "Exploratory unless paired repeated runs and independent qualification are recorded separately.",
        "packages": [],
    }
    failed = False
    for package in args.package or PACKAGES:
        repository = args.repositories / package
        driver = repository / "benchmarks" / "run.py"
        result = output / (package + ".json")
        row: dict[str, object] = {
            "package": package,
            "result": str(result),
            "started_at": time.time(),
        }
        try:
            if not driver.is_file():
                raise FileNotFoundError(f"Benchmark entry point is not available: {driver}")
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            row["driver_revision"] = revision
            row["driver_sha256"] = hashlib.sha256(driver.read_bytes()).hexdigest()
            row["driver_files_sha256"] = driver_fingerprints(driver.parent)
            with tempfile.TemporaryDirectory(prefix="aiogram-benchmark-driver-") as directory:
                row["installed"] = json.loads(
                    subprocess.check_output(
                        [str(executable), "-I", "-c", PROBE, package],
                        cwd=directory,
                        text=True,
                    )
                )
                probes = [row["installed"]]
                if args.profile == "native":
                    row["native_installed"] = json.loads(
                        subprocess.check_output(
                            [str(executable), "-I", "-c", PROBE, package + "-native"],
                            cwd=directory,
                            text=True,
                        )
                    )
                    if row["native_installed"]["version"] != row["installed"]["version"]:
                        raise ValueError("Native and base versions differ")
                    probes.append(row["native_installed"])
                environment = dict(os.environ)
                for variable in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE"):
                    environment.pop(variable, None)
                if args.redis_url:
                    for variable in (
                        "AIOGRAM_IDLE_REDIS_URL",
                        "AIOGRAM_NAV_REDIS_URL",
                        "SENTINEL_REDIS_URL",
                        "REDIS_URL",
                    ):
                        environment[variable] = args.redis_url
                command = benchmark_command(
                    executable,
                    probes,
                    driver,
                    "rust" if args.profile == "native" else "python",
                    result,
                    args.driver_arg,
                    quick=args.quick,
                )
                if args.redis_url and package in {"aiogram-nav", "aiogram-idle"}:
                    command.extend(["--redis-url", args.redis_url])
                row["command"] = command
                result.unlink(missing_ok=True)
                with (output / (package + ".log")).open("w") as log:
                    subprocess.run(
                        command,
                        cwd=directory,
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                        timeout=args.timeout,
                    )
                row["benchmark"] = json.loads(result.read_text())
                if driver_fingerprints(driver.parent) != row["driver_files_sha256"]:
                    raise ValueError(
                        "Benchmark driver changed during measurement; rerun the frozen driver"
                    )
                document = row["benchmark"]
                metadata = document.get("metadata", document)
                if metadata.get("engine") != ("rust" if args.profile == "native" else "python"):
                    raise ValueError("Driver reported a different engine")
                reported_version = metadata.get("package_version", metadata.get("version"))
                if (
                    metadata.get("package") != package
                    or reported_version != row["installed"]["version"]
                ):
                    raise ValueError("Driver reported a different installed package/version")
                document["run_id"] = str(uuid.uuid4())
                document["qualification_provenance"] = {
                    "base_artifact_sha256": row["installed"].get("artifact_sha256"),
                    "native_artifact_sha256": row.get("native_installed", {}).get(
                        "artifact_sha256"
                    ),
                    "driver_sha256": hashlib.sha256(
                        json.dumps(row["driver_files_sha256"], sort_keys=True).encode()
                    ).hexdigest(),
                }
                result.write_text(json.dumps(document, indent=2) + "\n")
            row["status"] = "completed"
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            row["status"] = "failed"
            row["error"] = str(error)
            failed = True
        row["finished_at"] = time.time()
        manifest["packages"].append(row)
        (output / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(package, row["status"], flush=True)
    manifest["finished_at"] = time.time()
    (output / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
