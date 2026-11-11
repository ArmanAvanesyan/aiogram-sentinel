# Cmds 0.3.0 qualification and release

The optimized Python distribution is published as 0.3.0 (PR18, merge
1457341dca31565335c9d53e22b9ae534dce9031). PyPI wheel/sdist hashes match the
reviewed release assets; a fresh index-only standalone install passed. The
optional Rust core is implemented and tested but its native distribution and
extra are **withheld** because the performance gate failed.

## Matched serial measurements

Six runs were performed serially on the host recorded in baseline-manifest.json:
published0.2 before, optimized Python A, Rust A, Rust B, Python B, published0.2
after. Individual JSON/manifests preserve installed-package provenance and driver
hashes. Normal runs use31 CPU samples and5 warmups; async tail measurements use
1000 individually measured operations on a persistent event loop. No universal
network or cross-host latency guarantee follows from these local workloads.

For the existing 100-command workload, the ratio of mean repeated optimized
Python CPU medians to the repeated published baseline is:

| Workload | Python0.3 / published0.2 CPU |
| --- | ---: |
| Profile resolution | 0.613 |
| Render and fingerprint | 0.657 |
| Confirmed unchanged profile | 0.588 |
| Fake Telegram delay1ms | 1.019 |

The fake-network path has no material measured CPU benefit. These workloads do
not imply every application gets the same improvement.

The native gate (`native-gate.json`) selected the representative compiled batch
of100 commands,10 profiles and30 targets. Rust/Python CPU ratio was1.567, so Rust
was about57% slower. Some small-menu tail ratios also exceeded1.05; several tail
profiles had over10% repeat spread and are inconclusive. The failed CPU gate alone
is sufficient to withhold native publication. Functional native wheels passed the
regular CPython3.10–3.14 and seven-platform CI matrix; functional compatibility is
separate from performance qualification.

## Supplemental compiled-manager probe

The sibling `../cmds-supplemental/` run uses the final published0.3.0 wheel. It is
explicitly a **quick exploratory probe**, not a replacement qualification run.
Within the same Python build, compiled versus dynamic confirmed-profile CPU ratios
were0.960,0.284 and0.070 for1,10 and100 commands respectively. Compiled snapshots
require explicit configuration and translation revisions; dynamic translators
remain uncached. Consumers must opt into that API and invalidate revisions when
inputs change. No native qualification or precise production latency claim is
made from this supplemental run.

## Release evidence

- GitHub release: https://github.com/ArmanAvanesyan/aiogram-cmds/releases/tag/v0.3.0
- Publish workflow: https://github.com/ArmanAvanesyan/aiogram-cmds/actions/runs/42927553362
- Wheel SHA256: a642c475f91808545bf0a33fd52d28b2e28e2f9bc17c18c78fe1cceab23f18db
- Sdist SHA256: 55fa79a1018d429887f8b4fcddb5b1567c1a0848f0f43b661af5b40642abe2dd

Exact release assets include SHA256SUMS and VERIFICATION.md. No native tag,
companion PyPI package or unavailable optional dependency was published.
