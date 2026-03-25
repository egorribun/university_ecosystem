#![no_main]

use libfuzzer_sys::fuzz_target;
use rust_ext::ScheduleItem;

// TD-22-03 (Wave 22): Fuzz Rust functions that do NOT require a Python runtime.
//
// Functions returning PyResult (get_partition_info, verify_audit_signature,
// batch_detect_conflicts) need an active Python GIL, which is incompatible
// with the extension-module feature used by PyO3. Those functions are covered
// by #[cfg(test)] unit tests in lib.rs (MOD-22-06).
//
// This fuzz target covers:
//   1. is_partition_expired  — partition name parsing (returns bool)
//   2. check_conflict_proto  — schedule conflict detection (pure logic)
//   3. parse_weekday         — weekday string parsing (pure logic)

fuzz_target!(|data: &[u8]| {
    // Only process valid UTF-8 — all Python strings are UTF-8.
    let s = match std::str::from_utf8(data) {
        Ok(v) => v,
        Err(_) => return,
    };

    // 1. Fuzz partition expiry — arbitrary partition names must not panic.
    let _ = rust_ext::is_partition_expired(
        s.to_string(),
        "audit_logs".to_string(),
        30,
    );

    // Also fuzz with adversarial table name.
    let _ = rust_ext::is_partition_expired(
        "tbl_y2025m01".to_string(),
        s.to_string(),
        30,
    );

    // 2. Fuzz weekday parsing — arbitrary strings must not panic.
    let _ = rust_ext::parse_weekday(s);

    // 3. Fuzz conflict detection — construct ScheduleItems directly
    //    (bypassing #[pymethods] new() which requires Python GIL).
    let a = ScheduleItem {
        id: None,
        weekday: s.to_string(),
        start_time: 0,
        end_time: 3600,
        parity: "both".to_string(),
    };
    let b = ScheduleItem {
        id: None,
        weekday: s.to_string(),
        start_time: 1800,
        end_time: 5400,
        parity: s.to_string(),
    };
    let _ = rust_ext::check_conflict_proto(&a, &b);
});
