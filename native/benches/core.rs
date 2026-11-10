use _aiogram_cmds_native::{encode_rows, fingerprint_encoded, resolve_profile};
use criterion::{BenchmarkId, Criterion, black_box, criterion_group, criterion_main};
fn profiles(c: &mut Criterion) {
    let mut group = c.benchmark_group("resolved_profile_cpu");
    for size in [1, 10, 100] {
        let names: Vec<String> = (0..size).map(|i| format!("command_{i}")).collect();
        let rows: Vec<_> = names
            .iter()
            .map(|n| (n.clone(), format!("Description {n}")))
            .collect();
        let encoded = encode_rows(&rows);
        group.bench_with_input(BenchmarkId::new("resolve", size), &names, |b, names| {
            b.iter(|| resolve_profile(black_box(names), &[], black_box(names)))
        });
        group.bench_with_input(
            BenchmarkId::new("fingerprint", size),
            &encoded,
            |b, value| {
                b.iter(|| {
                    fingerprint_encoded(
                        "123",
                        "{\"chat_id\":42,\"type\":\"chat\"}",
                        "null",
                        black_box(value),
                    )
                    .unwrap()
                })
            },
        );
    }
    group.finish();
}
criterion_group!(benches, profiles);
criterion_main!(benches);
