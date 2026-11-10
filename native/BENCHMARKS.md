# Native candidate: publication withheld

The original serial ABBA qualification failed. The selected workload
`compiled_batch/100/10_profiles/30_targets` had native/Python CPU ratio 1.56666
(native 56.7% slower). Dynamic `confirmation_hit/1` and `/10` p95 ratios were
1.1578 and 1.2001. Several end-to-end tails also showed more than 10% repeat spread,
so these results do not support a universal stable tail-latency claim.

The original failed gate stands. No native package, native tag or base dependency
extra will be published from this candidate. Rust source remains available for
explicit local builds; the default Python 0.3.0 release is independent.

Supplemental `compiled_confirmation_hit/{1,10,100}` and
`compiled_fake_telegram_1ms/{1,10,100}` workloads measure opt-in compiled manager
paths with a single event loop and 1000 individual latency samples in normal mode.
They account for Python SDK model construction and network fakes rather than
claiming pure core speedups transfer directly to updates. They supplement the
original workloads, never replace the failed gate or select a winning subset.
