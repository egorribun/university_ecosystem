use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use rust_ext::{batch_detect_conflicts, ScheduleItem};

fn make_items(n: usize) -> Vec<ScheduleItem> {
    assert!(
        n <= 576,
        "fixture exceeds two non-overlapping recurring days"
    );
    (0..n)
        .map(|i| ScheduleItem {
            id: Some(i as i32),
            // Keep the intended non-overlapping workload within a recurring
            // week; advancing reference dates no longer makes collisions vanish.
            weekday: if i % 2 == 0 { "monday" } else { "tuesday" }.to_string(),
            start_time: (i / 2) as i64 * 300,
            end_time: (i / 2) as i64 * 300 + 150,
            parity: "both".to_string(),
        })
        .collect()
}

fn bench_batch_detect(c: &mut Criterion) {
    let mut group = c.benchmark_group("batch_detect_conflicts");
    for size in [10, 50, 100, 500].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &size| {
            let items = make_items(size);
            assert!(matches!(batch_detect_conflicts(items.clone()), Ok(conflicts) if conflicts.is_empty()));
            b.iter(|| {
                let _ = batch_detect_conflicts(black_box(items.clone()));
            });
        });
    }
    group.finish();
}

criterion_group!(benches, bench_batch_detect);
criterion_main!(benches);
