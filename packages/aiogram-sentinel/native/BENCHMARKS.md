# Native qualification: publication withheld

The 2026-11-11 serial qualification did not meet the required 20% process CPU
improvement. **The native companion will not be published for this release.**
The core remains available from source for evaluation. There is no native-v tag,
native release or `[native]` extra. The optimized Python base 1.3.0 can be released
independently; Python remains the default.

The matched ABBA comparison used installed 1.3.0 artifacts with the final
surrogatepass byte-key implementation, two Python runs and two Rust runs,
50,000 operations per batch and 15 measured batch samples per run. The host was
macOS 15.8.1 x86_64, CPython 3.12.13, reporting 16 logical CPUs. These results apply
only to the measured host and workloads.

| Workload | Rust/Python process CPU ratio | Measured reduction | Required reduction |
| --- | ---: | ---: | ---: |
| Accepted rate-limit operations, many keys | 0.88350 | 11.65% | at least 20% |
| Accepted debounce operations, many keys | 0.92370 | 7.63% | at least 20% |

The middleware/fake-I/O update p95 ratio was 0.71225. However, repeated Python
latency measurements varied by more than 10%, failing the stability gate. This
ratio does **not** establish a tail-latency improvement. No universal speed or
latency claim follows from these measurements.

The later constructor-only ABI hardening validates exact capability types and
all kernel methods before exposing an engine. It changes neither the measured
hot paths nor the native artifact and does not qualify native performance.

See the [qualification decision and input hashes](../reports/native-serial-gate.json).
The older [development report](../reports/native-performance-development.md)
retains preliminary evidence; its quick samples are not qualification evidence.
Functional parity, artifact integrity and platform compatibility remain separate
checks and cannot substitute for the failed performance gate.
