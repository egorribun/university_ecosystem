#![deny(clippy::unwrap_used)]
use pyo3::prelude::*;
use rayon::prelude::*;
use chrono::{Utc, TimeZone, Datelike, Duration, NaiveDate, Weekday};

#[pyclass]
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
fn check_conflict_proto(a: &ScheduleItem, b: &ScheduleItem) -> bool {
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
    use std::sync::OnceLock;
    static POOL: OnceLock<rayon::ThreadPool> = OnceLock::new();
    let pool = POOL.get_or_init(|| {
        let threads = std::env::var("RUST_EXT_THREADS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(4);
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .expect("Failed to build rayon thread pool")
    });

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
fn parse_weekday(s: &str) -> Option<Weekday> {
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

#[pyclass]
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
fn get_partition_info(table_name: String, month_offset: i32) -> PyResult<PartitionInfo> {
    let now = Utc::now();
    let total_months = now.month() as i32 + month_offset;

    let target_year = now.year() + (total_months - 1) / 12;
    let target_month = ((total_months - 1) % 12 + 1) as u32;

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
fn is_partition_expired(partition_name: String, table_name: String, retention_days: i64) -> bool {
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
fn verify_audit_signature(signing_keys: Vec<String>, log_data: String, signature: String) -> PyResult<bool> {
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
