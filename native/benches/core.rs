use _aiogram_nav_native::{canonical_digest, history, json};
use criterion::{black_box, criterion_group, criterion_main, Criterion};
fn bench(c: &mut Criterion) {
    let payload = r#"{"hello":"Հայերեն 😀","integer":123456789012345678901234567890,"float":-0.0}"#;
    c.bench_function("strict_json", |b| {
        b.iter(|| json::parse(black_box(payload), 8_388_608, 64).unwrap())
    });
    c.bench_function("exact_fingerprint", |b| {
        b.iter(|| canonical_digest(black_box(payload)))
    });
    for count in [50, 500, 5000] {
        let nodes: Vec<_> = (0..count).map(|i|serde_json::json!({"id":format!("n{i}"),"parent":if i==0 {None}else{Some(format!("n{}",i-1))},"renderer":"r","back_to":null,"cancel_to":null})).collect();
        let raw =
            serde_json::json!({"roots":["n0"],"nodes":nodes,"migrations":{},"safe_root":null})
                .to_string();
        c.bench_function(&format!("registry_chain_compile_{count}"), |b| {
            b.iter(|| _aiogram_nav_native::registry::Graph::compile(black_box(&raw)).unwrap())
        });
    }
    for count in [50, 500, 5000] {
        let raw = serde_json::to_string(&vec![
            serde_json::json!({"node_id":"main","params":{"x":1}});
            count
        ])
        .unwrap();
        c.bench_function(&format!("history_trim_{count}"), |b| {
            b.iter(|| history(black_box(&raw), None, "none", 20, 1, false).unwrap())
        });
    }
}
criterion_group!(benches, bench);
criterion_main!(benches);
