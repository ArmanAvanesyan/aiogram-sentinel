# Installed-distribution performance evidence

Run this driver with each independently installed baseline/candidate environment.
The driver does not add the checkout's `src` directory to Python's search path.
The output records installed distribution/module provenance and hashes every
Python driver file. Editable installations require `--allow-editable`, which marks
the result exploratory. `--quick` is a smoke check, not qualification.

```sh
/path/to/installed/environment/bin/python benchmarks/run.py \
  --engine python --output /tmp/idle-python-run1.json \
  --redis-url redis://127.0.0.1:6379/0
```

Repeat serially twice per engine in the external qualification controller. Normal
mode collects ten independent CPU batches and at least 100 individual update
latencies. `memory-activate-touch/50` is the representative CPU workload: a fixed
session and draft with one activation per ten successful updates. Queue claiming
is separate. Raw CPU/latency arrays are retained; p95 uses nearest rank.
`qualification` is always false: only the external evaluator decides the CPU and
real-update latency gates. The script does not award a gate from microbenchmarks.

Standalone operation is the default and imports no navigation package. Add
`--combined` for application-rendered navigation adoption and a real
`Dispatcher.feed_update` no-op diagnostic. Rust combined operation requires both
exact-version native companions and fails if either is unavailable. Redis cases
use unique owned prefixes and remove only those prefixes; they never flush Redis.

Redis measurements count actual client `execute_command` calls, including library
coordination. Lua invocations and direct commands are separate. Argument bytes
are estimates, not full RESP/network bytes. Client elapsed time is not reported
as Lua server CPU. Post-timing SCAN/MEMORY USAGE/GET diagnostics report hot bytes,
retained storage and key count without charging those observation calls to an
update. Application authority is an immutable in-process implementation;
application FSM calls and cleanup calls are labeled separately.

Ages 1/10/50/500/5000 use fixed input size and bounded navigation history. The
latency trajectory explicitly configures enough receipt capacity; default
capacity admission and a short replay-window trajectory are reported separately.
Legacy combined snapshots above age 50 are explicitly unavailable rather than
allocating an unsafe quadratic baseline fixture. Admission failures remain
visible and must not be interpreted as a successful high-age latency result.

Useful controls: `--ages 1 10 50`, `--samples 100`, `--cpu-samples 10`,
`--skip-admission`, `--skip-redis`. Event-loop lag is a separate ready-task delay
diagnostic, outside the representative CPU timing.

## Format-three behavioral profile

```sh
AIOGRAM_IDLE_REDIS_URL=redis://127.0.0.1:16630/0 \
  uv run --no-sync python -m tests.profile_format3 --engine python \
  --combined --manifest /tmp/idle-format3-python-tests.json -q
```

The opt-in plugin supplies `storage_format=3` to production constructors before
work starts. It never activates storage inside an owned handler, replaces a
reducer, or bypasses a fence. Existing fault-injection script digests are retargeted
to the actual format-three scripts. Real killed-child tests use the same explicit
constructor profile. Legacy schema/activation tests still run in their original
profile; schema-specific corrupt-wire fixtures need equivalent format-three
assertions rather than interpreting a different wire layout as a failure.

For mixed engines, add `--nav-engine python` or `--nav-engine rust` to the test
profile. After standalone Python/Rust core runs, `--combined-only` runs just the
integration corpus for the other two engine combinations. Constructor defaults
are also propagated into genuine killed/crashed child processes. Explicit engine
choices inside cross-engine parity tests remain intact.

The shared evaluator reads only `results`: every row there has measured CPU
batches, their median and a call count. Non-timing evidence (event-loop lag,
admission outcomes and explicitly unavailable cases) lives in top-level
`diagnostics`. Comparison identity uses the deterministic input seed `0`.
