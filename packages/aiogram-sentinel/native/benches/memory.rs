use _aiogram_sentinel_native::{DebounceState, RateState};
use criterion::{Criterion, criterion_group, criterion_main};
use std::hint::black_box;

fn memory(c: &mut Criterion) {
    let mut rate = RateState::default();
    rate.allow(b"hot", 1, 60.0, 1000.0);
    c.bench_function("rate_rejected_hot", |b| {
        b.iter(|| rate.allow(black_box(b"hot"), 1, 60.0, 1000.0))
    });
    c.bench_function("rate_accepted_many", |b| {
        b.iter_batched(
            RateState::default,
            |mut state| {
                for i in 0..1000 {
                    state.allow(i.to_string().as_bytes(), 10, 60.0, 1000.0);
                }
            },
            criterion::BatchSize::SmallInput,
        )
    });
    let mut debounce = DebounceState::default();
    debounce.seen(b"hot", 60.0, b"fingerprint", 1000.0);
    c.bench_function("debounce_rejected_hot", |b| {
        b.iter(|| debounce.seen(black_box(b"hot"), 60.0, b"fingerprint", 1000.0))
    });
}
criterion_group!(benches, memory);
criterion_main!(benches);
