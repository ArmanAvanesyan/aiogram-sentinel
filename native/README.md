# aiogram-sentinel-native

Optional ABI1 synchronous memory kernels for aiogram-sentinel 1.3.0. The base
library remains a pure Python wheel. Install this companion only when choosing
`engine="rust"`; importing or using the default Python engine does not require it.
Rust performs no asynchronous I/O or application callbacks. Its memory state is
local to the process; Redis remains authoritative for distributed deployments.

Publication is withheld for 1.3.0 after the CPU qualification gate failed. The
core remains available from source, with no native release or base `[native]`
extra. See [the measured decision](BENCHMARKS.md); functional compatibility
does not imply a performance improvement.
