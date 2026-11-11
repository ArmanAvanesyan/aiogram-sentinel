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
from pathlib import Path

PACKAGES = ("aiogram-sentinel", "aiogram-cmds", "aiogram-nav", "aiogram-idle")
PROBE = """
import importlib, importlib.metadata, json, sys
name = sys.argv[1]
package = importlib.import_module(name.replace('-', '_'))
distribution = importlib.metadata.distribution(name)
direct = json.loads(distribution.read_text('direct_url.json') or '{}')
if direct.get('dir_info', {}).get('editable'):
    raise RuntimeError('Benchmark environment must install artifacts, not editable sources')
if 'site-packages' not in str(package.__file__):
    raise RuntimeError('Checkout shadows the benchmark distribution')
print(json.dumps({'distribution': name, 'version': distribution.version,
                  'module': str(package.__file__), 'python': sys.version,
                  'executable': sys.executable, 'direct_url': direct}))
"""


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
                environment = dict(os.environ)
                if args.redis_url:
                    for variable in (
                        "AIOGRAM_IDLE_REDIS_URL",
                        "AIOGRAM_NAV_REDIS_URL",
                        "SENTINEL_REDIS_URL",
                        "REDIS_URL",
                    ):
                        environment[variable] = args.redis_url
                command = [
                    str(executable),
                    str(driver),
                    "--engine",
                    "rust" if args.profile == "native" else "python",
                    "--output",
                    str(result),
                ]
                if args.quick:
                    command.append("--quick")
                command.extend(args.driver_arg)
                row["command"] = command
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
