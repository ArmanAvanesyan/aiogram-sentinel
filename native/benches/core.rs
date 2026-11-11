use _aiogram_idle_native::{core, queue::Queue};
use criterion::{black_box, criterion_group, criterion_main, Criterion};
fn benches(c: &mut Criterion) {
    c.bench_function("lifecycle_1000", |b| {
        b.iter(|| {
            for _ in 0..1000 {
                black_box(core::transition(
                    black_box("prompted"),
                    black_box("continue"),
                ));
            }
        })
    });
    let payload = "{\"flow\":\"feedback\",\"draft\":\"0123456789\"}".repeat(64);
    c.bench_function("canonical_sha256_3kb", |b| {
        b.iter(|| core::digest(black_box(&payload)))
    });
    c.bench_function("queue_schedule_claim_1000", |b| {
        b.iter(|| {
            let mut queue = Queue::default();
            for i in 0..1000 {
                queue
                    .schedule(
                        i.to_string(),
                        "bot".into(),
                        "1".into(),
                        Some(i as f64),
                        None,
                    )
                    .unwrap();
            }
            let tokens: Vec<_> = (0..1000).map(|i| format!("token-{i}")).collect();
            black_box(
                queue
                    .claim(1000, 60.0, 1000.0, &tokens, None, None)
                    .unwrap(),
            );
        })
    });
}
criterion_group!(core_benches, benches);
criterion_main!(core_benches);
