#![no_main]

use chrono::{Duration, TimeZone, Utc};
use libfuzzer_sys::fuzz_target;

struct ScheduleItem {
    weekday: String,
    start_time: i64,
    end_time: i64,
    parity: String,
}

fn check_conflict_proto(a: &ScheduleItem, b: &ScheduleItem) -> bool {
    if a.weekday != b.weekday {
        return false;
    }
    if a.parity != "both" && b.parity != "both" && a.parity != b.parity {
        return false;
    }
    a.start_time < b.end_time && b.start_time < a.end_time
}

fn parse_weekday(s: &str) -> bool {
    matches!(
        s.to_lowercase().as_str(),
        "monday"
            | "mon"
            | "tuesday"
            | "tue"
            | "wednesday"
            | "wed"
            | "thursday"
            | "thu"
            | "friday"
            | "fri"
            | "saturday"
            | "sat"
            | "sunday"
            | "sun"
    )
}

fn is_partition_expired(partition_name: &str, table_name: &str, retention_days: i64) -> bool {
    if retention_days < 0 {
        return false;
    }
    let prefix = format!("{table_name}_y");
    if !partition_name.starts_with(&prefix) {
        return false;
    }

    let parts: Vec<&str> = partition_name
        .trim_start_matches(&prefix)
        .split('m')
        .collect();
    if parts.len() != 2 {
        return false;
    }

    let p_year: i32 = match parts[0].parse() {
        Ok(v) => v,
        Err(_) => return false,
    };
    let p_month: u32 = match parts[1].parse() {
        Ok(v) => v,
        Err(_) => return false,
    };

    if p_year == 0 || p_month == 0 || p_month > 12 {
        return false;
    }

    let (next_year, next_month) = if p_month == 12 {
        (p_year + 1, 1)
    } else {
        (p_year, p_month + 1)
    };

    if let Some(p_end_date) = Utc
        .with_ymd_and_hms(next_year, next_month, 1, 0, 0, 0)
        .single()
    {
        let cutoff = Utc::now() - Duration::days(retention_days);
        return p_end_date < cutoff;
    }

    false
}

fuzz_target!(|data: &[u8]| {
    // Only process valid UTF-8 — all Python strings are UTF-8.
    let s = match std::str::from_utf8(data) {
        Ok(v) => v,
        Err(_) => return,
    };

    // 1. Fuzz partition expiry — arbitrary partition names must not panic.
    let _ = is_partition_expired(s, "audit_logs", 30);

    // Also fuzz with adversarial table name.
    let _ = is_partition_expired("tbl_y2025m01", s, 30);

    // 2. Fuzz weekday parsing — arbitrary strings must not panic.
    let _ = parse_weekday(s);

    // 3. Fuzz conflict detection — construct ScheduleItems directly
    //    (bypassing #[pymethods] new() which requires Python GIL).
    let a = ScheduleItem {
        weekday: s.to_string(),
        start_time: 0,
        end_time: 3600,
        parity: "both".to_string(),
    };
    let b = ScheduleItem {
        weekday: s.to_string(),
        start_time: 1800,
        end_time: 5400,
        parity: s.to_string(),
    };
    let _ = check_conflict_proto(&a, &b);
});
