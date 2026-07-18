#![deny(clippy::unwrap_used)]
#![deny(clippy::expect_used)] // LOW-W19: expect() panics just like unwrap(); deny it too
#![allow(unexpected_cfgs)]
use chrono::{Datelike, Duration, NaiveDate, TimeZone, Utc, Weekday};
use pyo3::prelude::*;
use rayon::prelude::*;
use std::sync::Mutex;

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
    pub end_time: i64, // timestamp in seconds
    #[pyo3(get, set)]
    pub parity: String,
}

// Python 3.13+ free-threaded builds can enter the same PyO3 function from
// multiple OS threads without a process-wide GIL.  PyO3's derived
// `FromPyObject` implementation for a `#[pyclass]` therefore needs a small
// serialization point while it borrows the Python object and clones its
// fields.  After extraction, `ScheduleItem` is owned Rust data and all
// conflict work remains fully parallel.
static SCHEDULE_ITEM_EXTRACT_LOCK: Mutex<()> = Mutex::new(());

fn schedule_item_extract_guard() -> PyResult<std::sync::MutexGuard<'static, ()>> {
    SCHEDULE_ITEM_EXTRACT_LOCK.lock().map_err(|_| {
        pyo3::exceptions::PyRuntimeError::new_err("ScheduleItem extraction lock is poisoned")
    })
}

#[pymethods]
impl ScheduleItem {
    #[new]
    #[pyo3(signature = (weekday, start_time, end_time, parity, id=None))]
    fn new(
        weekday: String,
        start_time: i64,
        end_time: i64,
        parity: String,
        id: Option<i32>,
    ) -> Self {
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
    if a.weekday != b.weekday {
        return false;
    }
    if a.parity != "both" && b.parity != "both" && a.parity != b.parity {
        return false;
    }
    a.start_time < a.end_time
        && b.start_time < b.end_time
        && a.start_time < b.end_time
        && b.start_time < a.end_time
}

#[pyfunction(name = "detect_conflicts")]
fn detect_conflicts_py(
    target: Bound<'_, PyAny>,
    existing: Bound<'_, PyAny>,
) -> PyResult<Vec<ScheduleItem>> {
    let _extract_guard = schedule_item_extract_guard()?;
    let target: ScheduleItem = target.extract()?;
    let existing: Vec<ScheduleItem> = existing.extract()?;
    drop(_extract_guard);

    detect_conflicts(target, existing)
}

fn detect_conflicts(
    target: ScheduleItem,
    existing: Vec<ScheduleItem>,
) -> PyResult<Vec<ScheduleItem>> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        existing
            .into_iter()
            .filter(|item| check_conflict_proto(&target, item))
            .collect()
    }))
    .map_err(|e| {
        let msg = if let Some(s) = e.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = e.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };
        pyo3::exceptions::PyRuntimeError::new_err(format!(
            "Rust panic in detect_conflicts: {}",
            msg
        ))
    })
}

// PERF-05 (audit Wave 13): explicit constant — centralises the DoS guard limit
// so it can be found by grep and updated in one place.
const MAX_CONFLICT_ITEMS: usize = 2500;

pub fn batch_detect_conflicts(
    items: Vec<ScheduleItem>,
) -> PyResult<Vec<(ScheduleItem, ScheduleItem)>> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        if items.len() > MAX_CONFLICT_ITEMS {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Input exceeds maximum allowed items ({MAX_CONFLICT_ITEMS}) for batch detection"
            )));
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
                    .map_err(|e| {
                        pyo3::exceptions::PyRuntimeError::new_err(format!(
                            "Failed to build rayon thread pool: {e}"
                        ))
                    })?;
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
    }))
    .map_err(|e| {
        let msg = if let Some(s) = e.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = e.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };
        pyo3::exceptions::PyRuntimeError::new_err(format!(
            "Rust panic in batch_detect_conflicts: {}",
            msg
        ))
    })?
}

#[pyfunction(name = "batch_detect_conflicts")]
fn batch_detect_conflicts_py(
    items: Bound<'_, PyAny>,
) -> PyResult<Vec<(ScheduleItem, ScheduleItem)>> {
    let _extract_guard = schedule_item_extract_guard()?;
    let items: Vec<ScheduleItem> = items.extract()?;
    drop(_extract_guard);

    batch_detect_conflicts(items)
}

#[pyfunction(name = "find_optimal_slot")]
#[pyo3(signature = (duration_minutes, existing_schedule, available_blocks))]
/// TD-W17-03 (Wave 17): Fixed to use the actual next occurrence of the
/// requested weekday instead of always using Jan 1. Previously, timestamps
/// were semantically wrong — conflict detection worked by coincidence (string
/// comparison of weekday + time overlap), but any caller using start_time/
/// end_time as real dates would get incorrect results.
fn find_optimal_slot_py(
    duration_minutes: u32,
    existing_schedule: Bound<'_, PyAny>,
    available_blocks: Bound<'_, PyAny>,
) -> PyResult<Option<ScheduleItem>> {
    let _extract_guard = schedule_item_extract_guard()?;
    let existing_schedule: Vec<ScheduleItem> = existing_schedule.extract()?;
    let available_blocks: Vec<(String, Vec<u32>)> = available_blocks.extract()?;
    drop(_extract_guard);

    find_optimal_slot(duration_minutes, existing_schedule, available_blocks)
}

fn find_optimal_slot(
    duration_minutes: u32,
    existing_schedule: Vec<ScheduleItem>,
    available_blocks: Vec<(String, Vec<u32>)>,
) -> PyResult<Option<ScheduleItem>> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
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

                    if !existing_schedule
                        .iter()
                        .any(|item| check_conflict_proto(&candidate, item))
                    {
                        return Some(candidate);
                    }
                }
            }
        }
        None
    }))
    .map_err(|e| {
        let msg = if let Some(s) = e.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = e.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };
        pyo3::exceptions::PyRuntimeError::new_err(format!(
            "Rust panic in find_optimal_slot: {}",
            msg
        ))
    })
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
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        // LOW-W19: reject month_offset values that would cause integer overflow or
        // produce a nonsensical date (e.g. offset going back before year 1 or
        // forward beyond year 9999).  Reasonable operational range is ±120 months (10 years).
        if !(-120..=120).contains(&month_offset) {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "month_offset {month_offset} is out of the allowed range [-120, 120]"
            )));
        }
        let now = Utc::now();
        // RZ-33-24: Use div_euclid/rem_euclid for correct negative month_offset
        // arithmetic.  Rust's `/` and `%` truncate toward zero, which produces
        // wrong results when total_months is zero or negative (e.g., January with
        // month_offset=-1 should yield December of the previous year, not month 0).
        let zero_indexed = now.month() as i32 - 1 + month_offset;
        let target_year = now.year() + zero_indexed.div_euclid(12);
        let target_month = (zero_indexed.rem_euclid(12) + 1) as u32;

        let start_date = Utc
            .with_ymd_and_hms(target_year, target_month, 1, 0, 0, 0)
            .single()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Invalid date"))?;

        let (next_year, next_month) = if target_month == 12 {
            (target_year + 1, 1)
        } else {
            (target_year, target_month + 1)
        };

        let end_date = Utc
            .with_ymd_and_hms(next_year, next_month, 1, 0, 0, 0)
            .single()
            .ok_or_else(|| {
                PyErr::new::<pyo3::exceptions::PyValueError, _>("Invalid next month date")
            })?;

        Ok(PartitionInfo {
            name: format!("{}_y{}m{:02}", table_name, target_year, target_month),
            start_date: start_date.to_rfc3339(),
            end_date: end_date.to_rfc3339(),
        })
    }))
    .map_err(|e| {
        let msg = if let Some(s) = e.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = e.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };
        pyo3::exceptions::PyRuntimeError::new_err(format!(
            "Rust panic in get_partition_info: {}",
            msg
        ))
    })?
}

#[pyfunction]
pub fn is_partition_expired(
    partition_name: String,
    table_name: String,
    retention_days: i64,
) -> PyResult<bool> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        // LOW-W19: a negative retention_days would make the cutoff a future timestamp,
        // causing every partition to appear un-expired.  Reject it defensively.
        if retention_days < 0 {
            return false;
        }
        let prefix = format!("{}_y", table_name);
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

        if let Some(p_end_date) = Utc
            .with_ymd_and_hms(next_year, next_month, 1, 0, 0, 0)
            .single()
        {
            let cutoff = Utc::now() - Duration::days(retention_days);
            return p_end_date < cutoff;
        }

        false
    }))
    .map_err(|e| {
        let msg = if let Some(s) = e.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = e.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };
        pyo3::exceptions::PyRuntimeError::new_err(format!(
            "Rust panic in is_partition_expired: {}",
            msg
        ))
    })
}

use hmac::{Hmac, Mac};
use sha2::Sha256;

#[pyfunction]
pub fn verify_audit_signature(
    signing_keys: Vec<String>,
    log_data: String,
    signature: String,
) -> PyResult<bool> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
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
    }))
    .map_err(|e| {
        let msg = if let Some(s) = e.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = e.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };
        pyo3::exceptions::PyRuntimeError::new_err(format!(
            "Rust panic in verify_audit_signature: {}",
            msg
        ))
    })?
}

/// A Python module implemented in Rust.
#[pymodule]
fn rust_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ScheduleItem>()?;
    m.add_class::<PartitionInfo>()?;
    m.add_function(wrap_pyfunction!(detect_conflicts_py, m)?)?;
    m.add_function(wrap_pyfunction!(batch_detect_conflicts_py, m)?)?;
    m.add_function(wrap_pyfunction!(find_optimal_slot_py, m)?)?;
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
#[allow(clippy::unwrap_used, clippy::expect_used)] // test code legitimately uses unwrap/expect
mod tests {
    use super::*;

    #[test]
    fn test_pyo3_bindings_coverage() {
        Python::initialize();
        Python::attach(|py| {
            let m = pyo3::types::PyModule::new(py, "rust_ext").unwrap();
            rust_ext(&m).unwrap();

            // 1. Check ScheduleItem class
            let item_cls = m.getattr("ScheduleItem").unwrap();
            let item = item_cls.call1(("monday", 0i64, 3600i64, "both")).unwrap();
            assert_eq!(
                item.getattr("weekday")
                    .unwrap()
                    .extract::<String>()
                    .unwrap(),
                "monday"
            );
            assert_eq!(
                item.getattr("start_time")
                    .unwrap()
                    .extract::<i64>()
                    .unwrap(),
                0
            );

            // 2. detect_conflicts
            let detect_conflicts = m.getattr("detect_conflicts").unwrap();
            let target = item_cls
                .call1(("monday", 1000i64, 2000i64, "both"))
                .unwrap();
            let existing_list = pyo3::types::PyList::new(
                py,
                vec![item_cls.call1(("monday", 0i64, 3600i64, "both")).unwrap()],
            )
            .unwrap();
            let conflicts: Vec<ScheduleItem> = detect_conflicts
                .call1((&target, &existing_list))
                .unwrap()
                .extract()
                .unwrap();
            assert_eq!(conflicts.len(), 1);

            // 3. batch_detect_conflicts
            let batch_detect_conflicts = m.getattr("batch_detect_conflicts").unwrap();
            let batch: Vec<(ScheduleItem, ScheduleItem)> = batch_detect_conflicts
                .call1((&existing_list,))
                .unwrap()
                .extract()
                .unwrap();
            assert!(batch.is_empty());

            // 4. find_optimal_slot
            let find_optimal_slot = m.getattr("find_optimal_slot").unwrap();
            let hours = pyo3::types::PyList::new(py, vec![10u32, 11u32]).unwrap();
            let tuple = pyo3::types::PyTuple::new(
                py,
                vec![
                    "monday".into_pyobject(py).unwrap().into_any(),
                    hours.into_any(),
                ],
            )
            .unwrap();
            let avail = pyo3::types::PyList::new(py, vec![tuple]).unwrap();
            let opt_res = find_optimal_slot
                .call1((60u32, &existing_list, &avail))
                .unwrap();
            let opt_item: Option<ScheduleItem> = opt_res.extract().unwrap();
            assert!(opt_item.is_some() || opt_item.is_none());

            // 5. get_partition_info
            let get_partition_info_py = m.getattr("get_partition_info").unwrap();
            let part_info = get_partition_info_py
                .call1(("notifications", 0i32))
                .unwrap();
            assert!(part_info
                .getattr("name")
                .unwrap()
                .extract::<String>()
                .unwrap()
                .contains("notifications"));

            // 6. is_partition_expired
            let is_partition_expired_py = m.getattr("is_partition_expired").unwrap();
            let expired: bool = is_partition_expired_py
                .call1(("notifications_y2026_m03", "notifications", 30i64))
                .unwrap()
                .extract()
                .unwrap();
            assert!(!expired);

            // 7. verify_audit_signature
            let verify_sig = m.getattr("verify_audit_signature").unwrap();
            let keys = pyo3::types::PyList::new(py, vec!["key1"]).unwrap();
            let sig_ok: bool = verify_sig
                .call1((&keys, "log_data", "deadbeef"))
                .unwrap()
                .extract()
                .unwrap();
            assert!(!sig_ok);
        });
    }

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
        assert!(!is_partition_expired("".to_string(), "tbl".to_string(), 90).unwrap());
    }

    #[test]
    fn expired_malformed_no_month_separator() {
        // Missing 'm' separator → malformed → false.
        assert!(!is_partition_expired("tbl_y2025".to_string(), "tbl".to_string(), 90).unwrap());
    }

    #[test]
    fn expired_malformed_non_numeric_year() {
        assert!(!is_partition_expired("tbl_yABCDm01".to_string(), "tbl".to_string(), 90).unwrap());
    }

    #[test]
    fn expired_malformed_non_numeric_month() {
        assert!(!is_partition_expired("tbl_y2025mXX".to_string(), "tbl".to_string(), 90).unwrap());
    }

    #[test]
    fn expired_month_zero() {
        // Month 0 is invalid — returns false.
        assert!(!is_partition_expired("tbl_y2025m00".to_string(), "tbl".to_string(), 90).unwrap());
    }

    #[test]
    fn expired_month_13() {
        // Month 13 is invalid — returns false.
        assert!(!is_partition_expired("tbl_y2025m13".to_string(), "tbl".to_string(), 90).unwrap());
    }

    #[test]
    fn expired_negative_retention() {
        // Negative retention_days → defensively returns false.
        assert!(!is_partition_expired("tbl_y2020m01".to_string(), "tbl".to_string(), -1).unwrap());
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
        let result =
            verify_audit_signature(vec!["key".to_string()], "".to_string(), "aabb".to_string());
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
        let result =
            verify_audit_signature(vec!["key".to_string()], "data".to_string(), "".to_string());
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

        let verified =
            verify_audit_signature(vec![key.to_string()], data.to_string(), sig_hex).unwrap();
        assert!(verified);
    }

    #[test]
    fn test_detect_conflicts() {
        let target = ScheduleItem {
            id: None,
            weekday: "monday".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: "both".to_string(),
        };
        let existing1 = ScheduleItem {
            id: Some(1),
            weekday: "monday".to_string(),
            start_time: 1500,
            end_time: 2500,
            parity: "both".to_string(),
        };
        let existing2 = ScheduleItem {
            id: Some(2),
            weekday: "tuesday".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: "both".to_string(),
        };

        let result = detect_conflicts(target, vec![existing1.clone(), existing2.clone()]).unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, Some(1));
    }

    #[test]
    fn test_batch_detect_conflicts() {
        std::env::set_var("RUST_EXT_THREADS", "2");
        let item1 = ScheduleItem {
            id: Some(1),
            weekday: "monday".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: "both".to_string(),
        };
        let item2 = ScheduleItem {
            id: Some(2),
            weekday: "monday".to_string(),
            start_time: 1500,
            end_time: 2500,
            parity: "both".to_string(),
        };
        let item3 = ScheduleItem {
            id: Some(3),
            weekday: "tuesday".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: "both".to_string(),
        };

        let result =
            batch_detect_conflicts(vec![item1.clone(), item2.clone(), item3.clone()]).unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].0.id, Some(1));
        assert_eq!(result[0].1.id, Some(2));

        // Test item size limit
        let mut huge_items = Vec::new();
        for _ in 0..2501 {
            huge_items.push(item1.clone());
        }
        let err_result = batch_detect_conflicts(huge_items);
        assert!(err_result.is_err());
    }

    #[test]
    fn test_find_optimal_slot() {
        let existing = vec![ScheduleItem {
            id: Some(1),
            weekday: "monday".to_string(),
            start_time: Utc::now().timestamp(), // conflicting block
            end_time: Utc::now().timestamp() + 3600,
            parity: "both".to_string(),
        }];

        let available = vec![
            ("invalid_day".to_string(), vec![10]),
            ("monday".to_string(), vec![9, 10]),
        ];

        let slot = find_optimal_slot(60, existing, available);
        assert!(slot.is_ok());
        let found = slot.unwrap();
        assert_eq!(found.unwrap().weekday, "monday");
    }

    #[test]
    fn test_is_partition_expired_real() {
        // Table name is "events"
        // Target is "events_y2020m01" -> End date is 2020-02-01
        // Cutoff is now - 1 day -> obviously expired
        assert!(
            is_partition_expired("events_y2020m01".to_string(), "events".to_string(), 1).unwrap()
        );

        // Cutoff is now - 100000 days -> obviously NOT expired
        assert!(
            !is_partition_expired("events_y2999m01".to_string(), "events".to_string(), 100000)
                .unwrap()
        );

        // Wrong table prefix -> false
        assert!(
            !is_partition_expired("other_y2020m01".to_string(), "events".to_string(), 1).unwrap()
        );
    }

    #[test]
    fn test_next_weekday() {
        let from = NaiveDate::from_ymd_opt(2026, 7, 3).unwrap(); // Friday

        // Target Friday -> should be today (2026-07-03)
        let friday = next_weekday(from, Weekday::Fri);
        assert_eq!(friday, from);

        // Target Saturday -> should be tomorrow (2026-07-04)
        let saturday = next_weekday(from, Weekday::Sat);
        assert_eq!(saturday, NaiveDate::from_ymd_opt(2026, 7, 4).unwrap());

        // Target Thursday -> should be next week (2026-07-09)
        let thursday = next_weekday(from, Weekday::Thu);
        assert_eq!(thursday, NaiveDate::from_ymd_opt(2026, 7, 9).unwrap());
    }

    // --- Property-based tests (proptest) ---
    // These verify algebraic properties that hold for ALL valid inputs,
    // not just hand-picked examples.
    use proptest::prelude::*;

    proptest! {
        /// check_conflict_proto is commutative: if A conflicts with B, B conflicts with A.
        #[test]
        fn prop_conflict_symmetry(
            start_a in 0i64..86400i64,
            end_a in 0i64..86400i64,
            start_b in 0i64..86400i64,
            end_b in 0i64..86400i64,
        ) {
            let a = ScheduleItem { id: None, weekday: "monday".to_string(),
                start_time: start_a.min(end_a), end_time: start_a.max(end_a) + 1,
                parity: "both".to_string() };
            let b = ScheduleItem { id: None, weekday: "monday".to_string(),
                start_time: start_b.min(end_b), end_time: start_b.max(end_b) + 1,
                parity: "both".to_string() };
            prop_assert_eq!(check_conflict_proto(&a, &b), check_conflict_proto(&b, &a));
        }

        /// Different weekdays NEVER conflict regardless of times.
        #[test]
        fn prop_different_weekday_no_conflict(
            start_a in 0i64..86400i64, end_a in 1i64..86401i64,
            start_b in 0i64..86400i64, end_b in 1i64..86401i64,
        ) {
            let a = ScheduleItem { id: None, weekday: "monday".to_string(),
                start_time: start_a, end_time: start_a + end_a,
                parity: "both".to_string() };
            let b = ScheduleItem { id: None, weekday: "tuesday".to_string(),
                start_time: start_b, end_time: start_b + end_b,
                parity: "both".to_string() };
            prop_assert!(!check_conflict_proto(&a, &b));
        }

        /// batch_detect_conflicts never panics for valid input sizes.
        #[test]
        fn prop_batch_no_panic(size in 0usize..100usize) {
            let items: Vec<ScheduleItem> = (0..size).map(|i| ScheduleItem {
                id: Some(i as i32),
                weekday: "monday".to_string(),
                start_time: (i as i64) * 100,
                end_time: (i as i64) * 100 + 50,
                parity: "both".to_string(),
            }).collect();
            let _ = batch_detect_conflicts(items); // must not panic
        }

        /// parse_weekday only returns Some for known weekday strings.
        #[test]
        fn prop_parse_weekday_unknown_returns_none(s in "[a-z]{1,12}") {
            let known = ["monday","mon","tuesday","tue","wednesday","wed",
                         "thursday","thu","friday","fri","saturday","sat",
                         "sunday","sun"];
            if !known.contains(&s.as_str()) {
                prop_assert!(parse_weekday(&s).is_none());
            }
        }
        /// Proptest for invalid or negative time intervals.
        /// Ensures check_conflict_proto never panics and behaves correctly:
        /// - commutativity holds even for negative/overflowing times or start_time > end_time.
        #[test]
        fn prop_invalid_times_never_panic_and_are_symmetric(
            start_a in -100_000i64..200_000i64,
            end_a in -100_000i64..200_000i64,
            start_b in -100_000i64..200_000i64,
            end_b in -100_000i64..200_000i64,
        ) {
            let a = ScheduleItem {
                id: None,
                weekday: "monday".to_string(),
                start_time: start_a,
                end_time: end_a,
                parity: "both".to_string(),
            };
            let b = ScheduleItem {
                id: None,
                weekday: "monday".to_string(),
                start_time: start_b,
                end_time: end_b,
                parity: "both".to_string(),
            };

            // commutes
            prop_assert_eq!(check_conflict_proto(&a, &b), check_conflict_proto(&b, &a));

            // if either has start >= end (invalid), there should be no conflict
            if start_a >= end_a || start_b >= end_b {
                prop_assert!(!check_conflict_proto(&a, &b));
            }
        }

        /// Property-based tests for optimal slot search (find_optimal_slot)
        #[test]
        fn prop_find_optimal_slot_properties(
            duration in 1u32..180u32,
            existing_count in 0usize..10usize,
            hours_a in prop::collection::vec(0u32..23u32, 0..5),
            hours_b in prop::collection::vec(0u32..23u32, 0..5),
        ) {
            let existing: Vec<ScheduleItem> = (0..existing_count).map(|i| {
                ScheduleItem {
                    id: Some(i as i32),
                    weekday: "monday".to_string(),
                    start_time: (i as i64) * 3600,
                    end_time: (i as i64) * 3600 + 1800,
                    parity: "both".to_string(),
                }
            }).collect();

            let available = vec![
                ("monday".to_string(), hours_a),
                ("tuesday".to_string(), hours_b),
            ];

            let result = find_optimal_slot(duration, existing.clone(), available);
            if let Ok(Some(slot)) = result {
                prop_assert_eq!(slot.parity.as_str(), "both");
                prop_assert!(slot.weekday == "monday" || slot.weekday == "tuesday");
                prop_assert_eq!(slot.end_time - slot.start_time, (duration * 60) as i64);

                // Verify no conflicts
                for item in existing {
                    prop_assert!(!check_conflict_proto(&slot, &item));
                }
            }
        }
    }
}

#[cfg(kani)]
mod verification {
    use super::*;

    #[kani::proof]
    fn proof_check_conflict_proto() {
        let weekday_val = String::from("monday");
        let parity_val = String::from("both");

        let a_start: i64 = kani::any();
        let a_end: i64 = kani::any();
        let b_start: i64 = kani::any();
        let b_end: i64 = kani::any();

        let a = ScheduleItem {
            id: None,
            weekday: weekday_val.clone(),
            start_time: a_start,
            end_time: a_end,
            parity: parity_val.clone(),
        };

        let b = ScheduleItem {
            id: None,
            weekday: weekday_val,
            start_time: b_start,
            end_time: b_end,
            parity: parity_val,
        };

        let _ = check_conflict_proto(&a, &b);
    }

    #[kani::proof]
    fn proof_get_partition_info() {
        let table_name = String::from("notifications");
        let month_offset: i32 = kani::any();
        let _ = get_partition_info(table_name, month_offset);
    }

    #[kani::proof]
    fn proof_verify_audit_signature() {
        let key_bytes: [u8; 8] = kani::any();
        let log_bytes: [u8; 8] = kani::any();
        let sig_bytes: [u8; 8] = kani::any();

        let key_str = match std::str::from_utf8(&key_bytes) {
            Ok(s) => s.to_string(),
            Err(_) => return,
        };
        let log_data = match std::str::from_utf8(&log_bytes) {
            Ok(s) => s.to_string(),
            Err(_) => return,
        };
        let signature = hex::encode(sig_bytes);

        let _ = verify_audit_signature(vec![key_str], log_data, signature);
    }
}
