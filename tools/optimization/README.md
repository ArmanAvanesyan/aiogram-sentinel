# Optimization evidence tools

These tools measure installed distributions and evaluate evidence. They do not
publish packages, change application configuration or deploy anything.

## Verify the tools

```sh
uv run --no-project --python 3.12 --with pytest --with pytest-asyncio \
  --with redis --with tomli pytest -q \
  -o asyncio_default_fixture_loop_scope=function tools/optimization/tests
uvx ruff check tools/optimization
```

The CI matrix runs CPython3.10,3.12 and3.14. The release artifact verifier requires
`tomli` on Python3.10; newer interpreters use `tomllib`.

## Installed-artifact measurements

Build and review the candidate base and native wheels in their owning repository.
Install the exact local artifacts into a fresh environment outside the checkout.
Keep their SHA256 manifests: qualification provenance uses the installed PEP610
archive digest and must match those independently reviewed release assets.
An index-only install without an archive digest can still be measured, but its
results cannot qualify a native release through this gate.

```sh
python3 tools/optimization/run_benchmarks.py \
  --python /tmp/candidate/bin/python --profile optimized \
  --package aiogram-nav --output-dir /tmp/nav-python-a \
  --driver-arg=--ages --driver-arg=50 --driver-arg=--skip-registry
```

Use `--profile native` for the matching companion; Python is the default engine.
Run at least twice per engine, serially, in a prespecified balanced order. Freeze
the drivers and all helper modules before the first run. The controller rejects
editable/source-shadowed packages, preimports the verified installed base/native
packages in an isolated interpreter, clears Python path overrides, fingerprints
all benchmark helper sources and checks reported engine/package/version. Every
result receives a unique run ID and artifact/driver provenance. No report alone
proves absence of host noise: review repeat spread and competing load.

`--quick` is exploratory. Run representative CPU workloads with at least10
independent samples and end-to-end latency workloads with at least100 individual
operations. Select CPU workloads before measuring rather than selecting a winning
subset afterward. Redis benchmarks use only dedicated test instances and owned
random prefixes; review each repository driver's options.

```sh
python3 tools/optimization/compare_results.py \
  --python /tmp/nav-python-a/aiogram-nav.json \
  --python /tmp/nav-python-b/aiogram-nav.json \
  --rust /tmp/nav-rust-a/aiogram-nav.json \
  --rust /tmp/nav-rust-b/aiogram-nav.json \
  --cpu-workload memory-track/50 --output /tmp/nav-native-gate.json
```

The comparator requires matching base artifacts, native artifacts within the Rust
profile, driver hashes and runtime/host identities. Duplicate paths, contents or
run IDs, zero/fractional/infinite sample counts and non-finite metrics fail closed.
CPU improvement must reach20%; individual-operation p95 must not regress by more
than5%, and repeat spread over10% withholds qualification. Historical reports
without new provenance remain readable but cannot qualify through the current
stricter gate. Earlier Sentinel/Cmds reports already failed the CPU gate and no
native companion was published from them.

## State growth and artifact verification

`benchmark_state_growth.py --help` describes standalone Nav, standalone Idle and
combined public-API workloads. Instrumentation separates client calls and computed
RESP request bytes from Lua-internal commands. Tracemalloc is off by default;
traced profiles are separate diagnostics, not CPU comparisons. Defaults preserve
library capacity settings; `--receipt-limit` is an explicit stress-test override.
Hot state and retained cold evidence are reported separately.

`verify_native_artifacts.py --help` verifies an exact companion release directory:
matching project/version/tag, exact wheel-platform allowlist, ABI3, distribution
metadata, module placement and independent checksums. `publish-native.yml` is the
reusable workflow template. Functional platform CI, clean wheel/sdist installs,
independent review and measured qualification remain separate required gates.
