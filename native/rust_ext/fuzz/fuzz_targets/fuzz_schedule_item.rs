#![no_main]
use arbitrary::Arbitrary;
use libfuzzer_sys::fuzz_target;

#[derive(Arbitrary, Debug)]
struct FuzzInput {
    start_time: i64,
    end_time: i64,
    parity_idx: u8,
}

fuzz_target!(|input: FuzzInput| {
    let parities = ["both", "odd", "even", "unknown", ""];
    let parity = parities[(input.parity_idx as usize) % parities.len()];
    let item = rust_ext::ScheduleItem {
        id: None,
        weekday: "monday".to_string(),
        start_time: input.start_time,
        end_time: input.end_time,
        parity: parity.to_string(),
    };
    let item2 = item.clone();
    // Must not panic regardless of input values
    let _ = rust_ext::check_conflict_proto(&item, &item2);
});
