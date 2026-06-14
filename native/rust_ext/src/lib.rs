#![deny(clippy::unwrap_used)]
#![deny(clippy::expect_used)] // LOW-W19: expect() panics just like unwrap(); deny it too
use pyo3::prelude::*;
use rayon::prelude::*;
use chrono::{Utc, TimeZone, Datelike, Duration, NaiveDate, Weekday};

// pyo3 0.29 (RUSTSEC-2026-0176/-0177 bump): the automatic FromPyObject derive
// for Clone #[pyclass] types is becoming opt-in. ScheduleItem is extracted from
// Python as Vec<ScheduleItem>/&ScheduleItem in the #[pyfunction]s below, so it
// needs the derive — opt in explicitly (behavior-preserving + forward-compatible
// with the pyo3 release that removes the auto-derive).
#[pyclass(from_py_object)]
#[derive(Clone, Debug)]
pub struct ScheduleItem {
    #[pyo3(get, set)]
    pub id: Option<i32>,
    #[pyo3(get, set)]
    pub weekday: String,
    #[pyo3(get, set)]
    pub start_time: i64, // timestamp in seconds
    #[pyo3(get, set)]
    pub end_time: i64,   // timestamp in seconds
    #[pyo3(get, set)]
    pub parity: String,
}

#[pymethods]
impl ScheduleItem {
    #[new]
    #[pyo3(signature = (weekday, start_time, end_time, parity, id=None))]
    fn new(weekday: String, start_time: i64, end_time: i64, parity: String, id: Option<i32>) -> Self {
        ScheduleItem {
            id,
            weekday,
            start_time,
            end_time,
            parity,
        }
    }
}

// Helper for conflict detection
pub fn check_conflict_proto(a: &ScheduleItem, b: &ScheduleItem) -> bool {
    if a.weekday != b.weekday { return false; }
    if a.parity != "both" && b.parity != "both" && a.parity != b.parity { return false; }
    a.start_time < b.end_time && b.start_time < a.end_time
}

#[pyfunction]
fn detect_conflicts(target: &ScheduleItem, existing: Vec<ScheduleItem>) -> Vec<ScheduleItem> {
    existing
        .into_iter()
        .filter(|item| check_conflict_proto(target, item))
        .collect()
}

// PERF-05 (audit Wave 13): explicit constant — centralises the DoS guard limit
// so it can be found by grep and updated in one place.
const MAX_CONFLICT_ITEMS: usize = 2500;

#[pyfunction]
fn batch_detect_conflicts(items: Vec<ScheduleItem>) -> PyResult<Vec<(ScheduleItem, ScheduleItem)>> {
    if items.len() > MAX_CONFLICT_ITEMS {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Input exceeds maximum allowed items ({MAX_CONFLICT_ITEMS}) for batch detection")
        ));
    }

    // TD-W18-02 (audit 2026-03-23 Wave 18): use a bounded thread pool instead of
    // rayon's global pool (which defaults to logical CPU count). On a 64-core
    // server this would spawn 64 threads; with Python free-threading (3.13+),
    // concurrent calls could saturate all CPU cores.
    //
    // LOW-W19: replaced .expect() with map_err()+? so a rayon build failure
    // surfaces as a Python RuntimeError instead of an unconditional panic.
    // OnceLock::get_or_init cannot return an error, so we initialise outside
    // the closure and cache only successfully-built pools.
    use std::sync::OnceLock;
    static POOL: OnceLock<rayon::ThreadPool> = OnceLock::new();
    let pool = match POOL.get() {
        Some(p) => p,
        None => {
            let threads = std::env::var("RUST_EXT_THREADS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(4usize);
            let built = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(
                    format!("Failed to build rayon thread pool: {e}")
                ))?;
            // If another thread raced us, discard our pool and use theirs.
            POOL.get_or_init(|| built)
        }
    };

    let conflicts = pool.install(|| {
        items
            .par_iter()
            .enumerate()
            .flat_map_iter(|(i, a)| {
                items[i + 1..]
                    .iter()
                    .filter(move |b| check_conflict_proto(a, b))
                    .map(move |b| (a.clone(), b.clone()))
            })
            .collect()
    });

    Ok(conflicts)
}

#[pyfunction]
#[pyo3(signature = (duration_minutes, existing_schedule, available_blocks))]
/// TD-W17-03 (Wave 17): Fixed to use the actual next occurrence of the
/// requested weekday instead of always using Jan 1. Previously, timestamps
/// were semantically wrong — conflict detection worked by coincidence (string
/// comparison of weekday + time overlap), but any caller using start_time/
/// end_time as real dates would get incorrect results.
fn find_optimal_slot(
    duration_minutes: u32,
    existing_schedule: Vec<ScheduleItem>,
    available_blocks: Vec<(String, Vec<u32>)>,
) -> Option<ScheduleItem> {
    let today = Utc::now().date_naive();

    for (day, hours) in available_blocks {
        // TD-W17-03: Resolve the actual next date matching this weekday.
        let target_wd = match parse_weekday(&day) {
            Some(wd) => wd,
            None => continue, // Skip unparseable weekday names.
        };
        let target_date = next_weekday(today, target_wd);

        for hour in hours {
            let start_date_time = target_date
                .and_hms_opt(hour, 0, 0)
                .map(|ndt| Utc.from_utc_datetime(&ndt));

            if let Some(start_dt) = start_date_time {
                let end_dt = start_dt + Duration::minutes(duration_minutes as i64);

                let candidate = ScheduleItem {
                    id: None,
                    weekday: day.clone(),
                    start_time: start_dt.timestamp(),
                    end_time: end_dt.timestamp(),
                    parity: "both".to_string(),
                };

                if !existing_schedule.iter().any(|item| check_conflict_proto(&candidate, item)) {
                    return Some(candidate);
                }
            }
        }
    }
    None
}

/// Find the next date (today or later) that falls on the given weekday.
fn next_weekday(from: NaiveDate, target: Weekday) -> NaiveDate {
    let current = from.weekday().num_days_from_monday();
    let target_num = target.num_days_from_monday();
    let days_ahead = (target_num as i64 - current as i64 + 7) % 7;
    // If today is the target weekday, use today (days_ahead == 0).
    from + Duration::days(days_ahead)
}

/// Parse a weekday string (case-insensitive) into a chrono Weekday.
pub fn parse_weekday(s: &str) -> Option<Weekday> {
    match s.to_lowercase().as_str() {
        "monday" | "mon" => Some(Weekday::Mon),
        "tuesday" | "tue" => Some(Weekday::Tue),
        "wednesday" | "wed" => Some(Weekday::Wed),
        "thursday" | "thu" => Some(Weekday::Thu),
        "friday" | "fri" => Some(Weekday::Fri),
        "saturday" | "sat" => Some(Weekday::Sat),
        "sunday" | "sun" => Some(Weekday::Sun),
        _ => None,
    }
}

// pyo3 0.29 (RUSTSEC-2026-0176/-0177 bump): the automatic FromPyObject derive
// for Clone #[pyclass] types is becoming opt-in. ScheduleItem is extracted from
// Python as Vec<ScheduleItem>/&ScheduleItem in the #[pyfunction]s below, so it
// needs the derive — opt in explicitly (behavior-preserving + forward-compatible
// with the pyo3 release that removes the auto-derive).
#[pyclass(from_py_object)]
#[derive(Clone, Debug)]
pub struct PartitionInfo {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub start_date: String,
    #[pyo3(get)]
    pub end_date: String,
}

#[pyfunction]
pub fn get_partition_info(table_name: String, month_offset: i32) -> PyResult<PartitionInfo> {
    // LOW-W19: reject month_offset values that would cause integer overflow or
    // produce a nonsensical date (e.g. offset going back before year 1 or
    // forward beyond year 9999).  Reasonable operational range is ±120 months (10 years).
    if month_offset < -120 || month_offset > 120 {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("month_offset {month_offset} is out of the allowed range [-120, 120]")
        ));
    }
    let now = Utc::now();
    // RZ-33-24: Use div_euclid/rem_euclid for correct negative month_offset
    // arithmetic.  Rust's `/` and `%` truncate toward zero, which produces
    // wrong results when total_months is zero or negative (e.g., January with
    // month_offset=-1 should yield December of the previous year, not month 0).
    let zero_indexed = now.month() as i32 - 1 + month_offset;
    let target_year = now.year() + zero_indexed.div_euclid(12);
    let target_month = (zero_indexed.rem_euclid(12) + 1) as u32;

    let start_date = Utc.with_ymd_and_hms(target_year, target_month, 1, 0, 0, 0)
        .single()
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Invalid date"))?;

    let (next_year, next_month) = if target_month == 12 {
        (target_year + 1, 1)
    } else {
        (target_year, target_month + 1)
    };

    let end_date = Utc.with_ymd_and_hms(next_year, next_month, 1, 0, 0, 0)
        .single()
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Invalid next month date"))?;

    Ok(PartitionInfo {
        name: format!("{}_y{}m{:02}", table_name, target_year, target_month),
        start_date: start_date.to_rfc3339(),
        end_date: end_date.to_rfc3339(),
    })
}

#[pyfunction]
pub fn is_partition_expired(partition_name: String, table_name: String, retention_days: i64) -> bool {
    // LOW-W19: a negative retention_days would make the cutoff a future timestamp,
    // causing every partition to appear un-expired.  Reject it defensively.
    if retention_days < 0 {
        return false;
    }
    let prefix = format!("{}_y", table_name);
    if !partition_name.starts_with(&prefix) {
        return false;
    }

    let parts: Vec<&str> = partition_name.trim_start_matches(&prefix).split('m').collect();
    if parts.len() != 2 {
        return false;
    }

    // TD-W17-04 (Wave 17): Explicit error handling instead of unwrap_or(0).
    // The previous pattern hid parse errors; a future refactor removing the
    // guard below would silently treat malformed partitions as valid.
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

    if let Some(p_end_date) = Utc.with_ymd_and_hms(next_year, next_month, 1, 0, 0, 0).single() {
        let cutoff = Utc::now() - Duration::days(retention_days);
        return p_end_date < cutoff;
    }

    false
}

use hmac::{Hmac, Mac};
use sha2::Sha256;

#[pyfunction]
pub fn verify_audit_signature(signing_keys: Vec<String>, log_data: String, signature: String) -> PyResult<bool> {
    let sig_bytes = match hex::decode(&signature) {
        Ok(b) => b,
        Err(_) => return Ok(false),
    };

    for key_str in signing_keys {
        let mut mac = Hmac::<Sha256>::new_from_slice(key_str.as_bytes())
            .map_err(|_| pyo3::exceptions::PyValueError::new_err("Invalid HMAC key length"))?;
        mac.update(log_data.as_bytes());
        if mac.verify_slice(&sig_bytes).is_ok() {
            return Ok(true);
        }
    }
    Ok(false)
}

/// A Python module implemented in Rust.
#[pymodule]
fn rust_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ScheduleItem>()?;
    m.add_class::<PartitionInfo>()?;
    m.add_function(wrap_pyfunction!(detect_conflicts, m)?)?;
    m.add_function(wrap_pyfunction!(batch_detect_conflicts, m)?)?;
    m.add_function(wrap_pyfunction!(find_optimal_slot, m)?)?;
    m.add_function(wrap_pyfunction!(get_partition_info, m)?)?;
    m.add_function(wrap_pyfunction!(is_partition_expired, m)?)?;
    m.add_function(wrap_pyfunction!(verify_audit_signature, m)?)?;
    // PERF-05: expose limit so Python callers can validate before calling into Rust.
    m.add("MAX_CONFLICT_ITEMS", MAX_CONFLICT_ITEMS)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// MOD-22-06 (audit 2026-03-25 Wave 22): Panic boundary tests for PyO3 FFI.
// Ensures edge cases in partition management, expiry checks, and HMAC
// verification return errors or safe defaults — never panic across the FFI.
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;

    // -- get_partition_info boundary tests --

    #[test]
    fn partition_info_boundary_minus_120() {
        // Minimum allowed offset — should succeed.
        let result = get_partition_info("audit_logs".to_string(), -120);
        assert!(result.is_ok(), "month_offset=-120 should be within range");
    }

    #[test]
    fn partition_info_boundary_plus_120() {
        // Maximum allowed offset — should succeed.
        let result = get_partition_info("audit_logs".to_string(), 120);
        assert!(result.is_ok(), "month_offset=120 should be within range");
    }

    #[test]
    fn partition_info_out_of_range_minus_121() {
        // One past the minimum — should return an error, not panic.
        let result = get_partition_info("audit_logs".to_string(), -121);
        assert!(result.is_err(), "month_offset=-121 should be rejected");
    }

    #[test]
    fn partition_info_out_of_range_plus_121() {
        // One past the maximum — should return an error, not panic.
        let result = get_partition_info("audit_logs".to_string(), 121);
        assert!(result.is_err(), "month_offset=121 should be rejected");
    }

    #[test]
    fn partition_info_zero_offset() {
        let result = get_partition_info("events".to_string(), 0);
        assert!(result.is_ok());
        let info = result.ok().unwrap();
        assert!(info.name.starts_with("events_y"));
    }

    // -- is_partition_expired edge cases --

    #[test]
    fn expired_empty_partition_name() {
        // Empty name cannot match the expected prefix — returns false.
        assert!(!is_partition_expired("".to_string(), "tbl".to_string(), 90));
    }

    #[test]
    fn expired_malformed_no_month_separator() {
        // Missing 'm' separator → malformed → false.
        assert!(!is_partition_expired("tbl_y2025".to_string(), "tbl".to_string(), 90));
    }

    #[test]
    fn expired_malformed_non_numeric_year() {
        assert!(!is_partition_expired("tbl_yABCDm01".to_string(), "tbl".to_string(), 90));
    }

    #[test]
    fn expired_malformed_non_numeric_month() {
        assert!(!is_partition_expired("tbl_y2025mXX".to_string(), "tbl".to_string(), 90));
    }

    #[test]
    fn expired_month_zero() {
        // Month 0 is invalid — returns false.
        assert!(!is_partition_expired("tbl_y2025m00".to_string(), "tbl".to_string(), 90));
    }

    #[test]
    fn expired_month_13() {
        // Month 13 is invalid — returns false.
        assert!(!is_partition_expired("tbl_y2025m13".to_string(), "tbl".to_string(), 90));
    }

    #[test]
    fn expired_negative_retention() {
        // Negative retention_days → defensively returns false.
        assert!(!is_partition_expired("tbl_y2020m01".to_string(), "tbl".to_string(), -1));
    }

    // -- verify_audit_signature edge cases --

    #[test]
    fn signature_empty_keys_list() {
        // No keys → no match → false (not an error).
        let result = verify_audit_signature(vec![], "data".to_string(), "aabb".to_string());
        assert!(result.is_ok());
        assert!(!result.ok().unwrap());
    }

    #[test]
    fn signature_empty_data() {
        // Empty data is valid input — HMAC of empty string is well-defined.
        let result = verify_audit_signature(
            vec!["key".to_string()],
            "".to_string(),
            "aabb".to_string(),
        );
        assert!(result.is_ok());
        // The signature won't match, but it must not panic.
        assert!(!result.ok().unwrap());
    }

    #[test]
    fn signature_invalid_hex() {
        // Non-hex signature string → graceful false return.
        let result = verify_audit_signature(
            vec!["key".to_string()],
            "data".to_string(),
            "not-valid-hex!!".to_string(),
        );
        assert!(result.is_ok());
        assert!(!result.ok().unwrap());
    }

    #[test]
    fn signature_empty_signature() {
        // Empty signature string → hex::decode("") returns empty vec → verify fails.
        let result = verify_audit_signature(
            vec!["key".to_string()],
            "data".to_string(),
            "".to_string(),
        );
        assert!(result.is_ok());
        assert!(!result.ok().unwrap());
    }

    #[test]
    fn test_parse_weekday() {
        assert_eq!(parse_weekday("monday"), Some(Weekday::Mon));
        assert_eq!(parse_weekday("MON"), Some(Weekday::Mon));
        assert_eq!(parse_weekday("Friday"), Some(Weekday::Fri));
        assert_eq!(parse_weekday("invalid"), None);
    }

    #[test]
    fn test_check_conflict_proto() {
        let item1 = ScheduleItem {
            id: None,
            weekday: "monday".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: "both".to_string(),
        };
        let item2 = ScheduleItem {
            id: None,
            weekday: "monday".to_string(),
            start_time: 1500,
            end_time: 2500,
            parity: "both".to_string(),
        };
        let item3 = ScheduleItem {
            id: None,
            weekday: "tuesday".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: "both".to_string(),
        };

        // Conflicting: same weekday, overlapping times, parity "both"
        assert!(check_conflict_proto(&item1, &item2));
        // Not conflicting: different weekdays
        assert!(!check_conflict_proto(&item1, &item3));
    }

    #[test]
    fn signature_verification_success() {
        let key = "my-secret-key";
        let data = "test-log-data";
        
        let mut mac = Hmac::<Sha256>::new_from_slice(key.as_bytes()).unwrap();
        mac.update(data.as_bytes());
        let result_bytes = mac.finalize().into_bytes();
        let sig_hex = hex::encode(result_bytes);
        
        let verified = verify_audit_signature(vec![key.to_string()], data.to_string(), sig_hex).unwrap();
        assert!(verified);
    }
}
