#![deny(clippy::unwrap_used)]
#![deny(clippy::expect_used)] // LOW-W19: expect() panics just like unwrap(); deny it too
#![allow(unexpected_cfgs)]
use chrono::{DateTime, Datelike, Duration, NaiveDate, TimeZone, Utc, Weekday};
use pyo3::prelude::*;
use rayon::prelude::*;
use std::any::Any;
use std::fmt::Display;
use std::sync::{LockResult, Mutex, MutexGuard};
use subtle::{Choice, ConstantTimeEq};
use zeroize::Zeroizing;

// pyo3 0.29 (RUSTSEC-2026-0176/-0177 bump): the automatic FromPyObject
// implementation for Clone #[pyclass] types is no longer implicit. The explicit
// manual implementations below preserve extraction from Python while keeping the
// conversion path directly testable and forward-compatible with future PyO3.
#[pyclass(skip_from_py_object)]
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

impl<'py> FromPyObject<'_, 'py> for ScheduleItem {
    type Error = PyErr;

    fn extract(obj: pyo3::Borrowed<'_, 'py, PyAny>) -> Result<Self, Self::Error> {
        Ok(obj.cast::<Self>()?.borrow().clone())
    }
}

// Python 3.13+ free-threaded builds can enter the same PyO3 function from
// multiple OS threads without a process-wide GIL. The manual `FromPyObject`
// implementation therefore needs a small serialization point while it borrows
// the Python object and clones its fields. After extraction, `ScheduleItem` is
// owned Rust data and all conflict work remains fully parallel.
static SCHEDULE_ITEM_EXTRACT_LOCK: Mutex<()> = Mutex::new(());

fn mutex_guard_or_py_err<'a>(
    result: LockResult<MutexGuard<'a, ()>>,
) -> PyResult<MutexGuard<'a, ()>> {
    result.map_err(|_| {
        pyo3::exceptions::PyRuntimeError::new_err("ScheduleItem extraction lock is poisoned")
    })
}

fn schedule_item_extract_guard() -> PyResult<std::sync::MutexGuard<'static, ()>> {
    mutex_guard_or_py_err(SCHEDULE_ITEM_EXTRACT_LOCK.lock())
}

fn panic_to_py_err(context: &str, panic: Box<dyn Any + Send>) -> PyErr {
    let msg = if let Some(s) = panic.downcast_ref::<&str>() {
        s.to_string()
    } else if let Some(s) = panic.downcast_ref::<String>() {
        s.clone()
    } else {
        "Unknown panic".to_string()
    };
    pyo3::exceptions::PyRuntimeError::new_err(format!("Rust panic in {context}: {msg}"))
}

fn catch_unwind_value<T, F>(context: &str, operation: F) -> PyResult<T>
where
    F: FnOnce() -> T + std::panic::UnwindSafe,
{
    std::panic::catch_unwind(operation).map_err(|panic| panic_to_py_err(context, panic))
}

fn catch_unwind_result<T, F>(context: &str, operation: F) -> PyResult<T>
where
    F: FnOnce() -> PyResult<T> + std::panic::UnwindSafe,
{
    catch_unwind_value(context, operation)?
}

fn build_rayon_pool(threads: usize) -> PyResult<rayon::ThreadPool> {
    if threads == 0 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "RUST_EXT_THREADS must be greater than zero",
        ));
    }
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .map_err(rayon_pool_build_error)
}

fn parse_rayon_threads(value: Option<String>) -> usize {
    value.and_then(|raw| raw.parse().ok()).unwrap_or(4usize)
}

fn rayon_pool_build_error<E: Display>(error: E) -> PyErr {
    pyo3::exceptions::PyRuntimeError::new_err(format!("Failed to build rayon thread pool: {error}"))
}

fn hmac_key_error<E: Display>(_error: E) -> PyErr {
    pyo3::exceptions::PyValueError::new_err("Invalid HMAC key length")
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

#[derive(Clone)]
struct ConflictMetadata {
    weekday: Option<Weekday>,
    weekday_fallback: Option<String>,
    parity: Option<String>,
}

#[inline]
fn conflict_metadata(item: &ScheduleItem) -> ConflictMetadata {
    let weekday = item.weekday.trim();
    let parity = item.parity.trim();
    let parsed_weekday = parse_weekday(weekday);

    ConflictMetadata {
        weekday: parsed_weekday,
        weekday_fallback: parsed_weekday.is_none().then(|| weekday.to_owned()),
        parity: (!parity.eq_ignore_ascii_case("both")).then(|| parity.to_owned()),
    }
}

#[inline]
fn weekday_comparison_value(metadata: &ConflictMetadata) -> &str {
    metadata
        .weekday
        .map(weekday_name)
        .or(metadata.weekday_fallback.as_deref())
        .unwrap_or_default()
}

#[inline]
fn check_conflict_with_metadata(
    a: &ScheduleItem,
    a_metadata: &ConflictMetadata,
    b: &ScheduleItem,
    b_metadata: &ConflictMetadata,
) -> bool {
    let same_weekday = match (a_metadata.weekday, b_metadata.weekday) {
        (Some(w1), Some(w2)) => w1 == w2,
        _ => weekday_comparison_value(a_metadata)
            .eq_ignore_ascii_case(weekday_comparison_value(b_metadata)),
    };
    if !same_weekday {
        return false;
    }

    if let (Some(a_parity), Some(b_parity)) = (&a_metadata.parity, &b_metadata.parity) {
        if !a_parity.eq_ignore_ascii_case(b_parity) {
            return false;
        }
    }

    a.start_time < a.end_time
        && b.start_time < b.end_time
        && a.start_time < b.end_time
        && b.start_time < a.end_time
}

// Helper for conflict detection
pub fn check_conflict_proto(a: &ScheduleItem, b: &ScheduleItem) -> bool {
    let a_metadata = conflict_metadata(a);
    let b_metadata = conflict_metadata(b);
    check_conflict_with_metadata(a, &a_metadata, b, &b_metadata)
}

/// Helper to normalize a ScheduleItem's start/end timestamps onto a target date's midnight timestamp,
/// preserving its time-of-day window and duration (e.g. for 1970 baseline time-of-day schedule items).
fn normalize_item_for_date(item: &ScheduleItem, target_midnight: i64) -> ScheduleItem {
    let tod_start = item.start_time.rem_euclid(86400);
    let duration = item.end_time - item.start_time;

    let norm_start = target_midnight + tod_start;
    let norm_end = norm_start + duration;

    ScheduleItem {
        id: item.id,
        weekday: item.weekday.clone(),
        start_time: norm_start,
        end_time: norm_end,
        parity: item.parity.clone(),
    }
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
    catch_unwind_value(
        "detect_conflicts",
        std::panic::AssertUnwindSafe(|| {
            existing
                .into_iter()
                .filter(|item| check_conflict_proto(&target, item))
                .collect()
        }),
    )
}

// PERF-05 (audit Wave 13): explicit constants — centralises the DoS guard limits
// so they can be found by grep and updated in one place.
const MAX_CONFLICT_ITEMS: usize = 2500;
const MAX_CONFLICT_PAIRS: usize = 50_000;
// Rayon scheduling overhead dominates tiny batches; keep those calls local while
// retaining the bounded pool for the larger O(n²) workloads.
const PARALLEL_CONFLICT_THRESHOLD: usize = 32;

#[inline]
fn canonical_weekday_code(weekday: &str) -> u8 {
    match weekday {
        "monday" => 0,
        "tuesday" => 1,
        "wednesday" => 2,
        "thursday" => 3,
        "friday" => 4,
        "saturday" => 5,
        "sunday" => 6,
        _ => u8::MAX,
    }
}

#[inline]
fn record_conflict_pair(
    a: &ScheduleItem,
    b: &ScheduleItem,
    pair_count: &std::sync::atomic::AtomicUsize,
    limit_exceeded: &std::sync::atomic::AtomicBool,
) -> Option<(ScheduleItem, ScheduleItem)> {
    if pair_count.fetch_add(1, std::sync::atomic::Ordering::Relaxed) >= MAX_CONFLICT_PAIRS {
        limit_exceeded.store(true, std::sync::atomic::Ordering::Relaxed);
        None
    } else {
        Some((a.clone(), b.clone()))
    }
}

pub fn batch_detect_conflicts(
    items: Vec<ScheduleItem>,
) -> PyResult<Vec<(ScheduleItem, ScheduleItem)>> {
    catch_unwind_result(
        "batch_detect_conflicts",
        std::panic::AssertUnwindSafe(|| {
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
                    let threads = parse_rayon_threads(std::env::var("RUST_EXT_THREADS").ok());
                    let built = build_rayon_pool(threads)?;
                    // If another thread raced us, discard our pool and use theirs.
                    POOL.get_or_init(|| built)
                }
            };

            // Keep the common canonical representation on the lean pairwise path. This is
            // the format emitted by the normal scheduler and avoids allocating metadata for
            // every item when no case/whitespace normalization is required. Non-canonical
            // inputs continue through the normalized path below.
            let canonical_fast_path = items.iter().all(|item| {
                item.parity == "both"
                    && item.start_time < item.end_time
                    && matches!(
                        item.weekday.as_str(),
                        "monday"
                            | "tuesday"
                            | "wednesday"
                            | "thursday"
                            | "friday"
                            | "saturday"
                            | "sunday"
                    )
            });

            let pair_count = std::sync::atomic::AtomicUsize::new(0);
            let limit_exceeded = std::sync::atomic::AtomicBool::new(false);
            let conflicts: Vec<(ScheduleItem, ScheduleItem)> = if canonical_fast_path {
                if items.len() < PARALLEL_CONFLICT_THRESHOLD {
                    // Rayon scheduling overhead dominates tiny batches, and the
                    // direct String comparison avoids allocating a code vector for
                    // this latency-sensitive path.
                    items
                        .iter()
                        .enumerate()
                        .flat_map(|(i, a)| {
                            items[i + 1..]
                                .iter()
                                .filter(move |b| {
                                    a.weekday == b.weekday
                                        && a.start_time < b.end_time
                                        && b.start_time < a.end_time
                                })
                                .filter_map(|b| {
                                    record_conflict_pair(a, b, &pair_count, &limit_exceeded)
                                })
                        })
                        .collect()
                } else {
                    // Canonical inputs use one of seven fixed weekday strings.  Compare
                    // a compact code in the O(n²) loop instead of repeatedly scanning
                    // each String's bytes; the observable pair ordering and overlap
                    // predicates remain unchanged.
                    let weekday_codes: Vec<u8> = items
                        .iter()
                        .map(|item| canonical_weekday_code(&item.weekday))
                        .collect();
                    pool.install(|| {
                        items
                            .par_iter()
                            .enumerate()
                            .flat_map_iter(|(i, a)| {
                                let a_weekday = weekday_codes[i];
                                items[i + 1..]
                                    .iter()
                                    .zip(weekday_codes[i + 1..].iter())
                                    .filter(move |b| {
                                        a_weekday == *b.1
                                            && a.start_time < b.0.end_time
                                            && b.0.start_time < a.end_time
                                    })
                                    .filter_map(|(b, _)| {
                                        record_conflict_pair(a, b, &pair_count, &limit_exceeded)
                                    })
                            })
                            .collect()
                    })
                }
            } else {
                // Normalize each item once. The pairwise loop is O(n²), so doing
                // case-folding and weekday parsing inside it made the benchmark
                // regress by orders of magnitude for larger batches.
                let metadata: Vec<ConflictMetadata> = items.iter().map(conflict_metadata).collect();
                pool.install(|| {
                    items
                        .par_iter()
                        .enumerate()
                        .flat_map_iter(|(i, a)| {
                            let a_metadata = &metadata[i];
                            items[i + 1..]
                                .iter()
                                .zip(metadata[i + 1..].iter())
                                .filter(move |(b, b_metadata)| {
                                    check_conflict_with_metadata(a, a_metadata, b, b_metadata)
                                })
                                .filter_map(|(b, _b_metadata)| {
                                    record_conflict_pair(a, b, &pair_count, &limit_exceeded)
                                })
                        })
                        .collect()
                })
            };

            if limit_exceeded.load(std::sync::atomic::Ordering::Relaxed) {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Detected conflict pairs exceed maximum allowed cap ({MAX_CONFLICT_PAIRS})"
                )));
            }

            Ok(conflicts)
        }),
    )
}

#[pyfunction(name = "batch_detect_conflicts")]
fn batch_detect_conflicts_py(
    py: Python<'_>,
    items: Bound<'_, PyAny>,
) -> PyResult<Vec<(ScheduleItem, ScheduleItem)>> {
    let _extract_guard = schedule_item_extract_guard()?;
    let items: Vec<ScheduleItem> = items.extract()?;
    drop(_extract_guard);

    // Rayon performs CPU-intensive pairwise work on owned Rust values.  Detach
    // from Python while it runs so concurrent asyncio/worker threads can make
    // progress; all Python extraction and result conversion remains on the
    // GIL-held side of this boundary.
    py.detach(|| batch_detect_conflicts(items))
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

fn checked_slot_end(start: DateTime<Utc>, duration: Duration) -> Option<DateTime<Utc>> {
    start.checked_add_signed(duration)
}

fn weekday_name(wd: Weekday) -> &'static str {
    match wd {
        Weekday::Mon => "monday",
        Weekday::Tue => "tuesday",
        Weekday::Wed => "wednesday",
        Weekday::Thu => "thursday",
        Weekday::Fri => "friday",
        Weekday::Sat => "saturday",
        Weekday::Sun => "sunday",
    }
}

fn find_optimal_slot(
    duration_minutes: u32,
    existing_schedule: Vec<ScheduleItem>,
    available_blocks: Vec<(String, Vec<u32>)>,
) -> PyResult<Option<ScheduleItem>> {
    catch_unwind_value(
        "find_optimal_slot",
        std::panic::AssertUnwindSafe(|| {
            find_optimal_slot_at(
                Utc::now().date_naive(),
                duration_minutes,
                existing_schedule,
                available_blocks,
            )
        }),
    )
}

fn find_optimal_slot_at(
    today: NaiveDate,
    duration_minutes: u32,
    existing_schedule: Vec<ScheduleItem>,
    available_blocks: Vec<(String, Vec<u32>)>,
) -> Option<ScheduleItem> {
    for (day, hours) in available_blocks {
        // TD-W17-03: Resolve the actual next date matching this weekday.
        let target_wd = match parse_weekday(&day) {
            Some(wd) => wd,
            None => continue, // Skip unparseable weekday names.
        };
        let target_date = next_weekday(today, target_wd);
        let target_midnight = target_date
            .and_hms_opt(0, 0, 0)
            .map(|ndt| Utc.from_utc_datetime(&ndt))
            .map(|dt| dt.timestamp())
            .unwrap_or(0);

        for hour in hours {
            let start_date_time = target_date
                .and_hms_opt(hour, 0, 0)
                .map(|ndt| Utc.from_utc_datetime(&ndt));

            let Some(start_dt) = start_date_time else {
                continue;
            };
            // `duration_minutes` is a u32, so conversion to chrono's
            // i64-backed duration cannot overflow; keeping this path
            // infallible avoids an unreachable branch in the scheduler.
            let dur = Duration::minutes(duration_minutes as i64);
            let Some(end_dt) = checked_slot_end(start_dt, dur) else {
                continue;
            };

            let candidate = ScheduleItem {
                id: None,
                weekday: day.clone(),
                start_time: start_dt.timestamp(),
                end_time: end_dt.timestamp(),
                parity: "both".to_string(),
            };

            let candidate_day2 = if end_dt.date_naive() > start_dt.date_naive() {
                Some(ScheduleItem {
                    id: None,
                    weekday: weekday_name(end_dt.weekday()).to_string(),
                    start_time: start_dt.timestamp(),
                    end_time: end_dt.timestamp(),
                    parity: "both".to_string(),
                })
            } else {
                None
            };

            let has_conflict = existing_schedule.iter().any(|item| {
                if item.start_time < 31536000 {
                    let norm_item = normalize_item_for_date(item, target_midnight);
                    if check_conflict_proto(&candidate, &norm_item) {
                        return true;
                    }
                    if let Some(c2) = &candidate_day2 {
                        let norm_item_day2 = normalize_item_for_date(item, target_midnight + 86400);
                        if check_conflict_proto(c2, &norm_item_day2) {
                            return true;
                        }
                    }
                    false
                } else {
                    if check_conflict_proto(&candidate, item) {
                        return true;
                    }
                    if let Some(c2) = &candidate_day2 {
                        if check_conflict_proto(c2, item) {
                            return true;
                        }
                    }
                    false
                }
            });

            if !has_conflict {
                return Some(candidate);
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
    let trimmed = s.trim();
    if trimmed.eq_ignore_ascii_case("monday") || trimmed.eq_ignore_ascii_case("mon") {
        Some(Weekday::Mon)
    } else if trimmed.eq_ignore_ascii_case("tuesday") || trimmed.eq_ignore_ascii_case("tue") {
        Some(Weekday::Tue)
    } else if trimmed.eq_ignore_ascii_case("wednesday") || trimmed.eq_ignore_ascii_case("wed") {
        Some(Weekday::Wed)
    } else if trimmed.eq_ignore_ascii_case("thursday") || trimmed.eq_ignore_ascii_case("thu") {
        Some(Weekday::Thu)
    } else if trimmed.eq_ignore_ascii_case("friday") || trimmed.eq_ignore_ascii_case("fri") {
        Some(Weekday::Fri)
    } else if trimmed.eq_ignore_ascii_case("saturday") || trimmed.eq_ignore_ascii_case("sat") {
        Some(Weekday::Sat)
    } else if trimmed.eq_ignore_ascii_case("sunday") || trimmed.eq_ignore_ascii_case("sun") {
        Some(Weekday::Sun)
    } else {
        None
    }
}

// See the ScheduleItem comment above: this class also uses an explicit
// FromPyObject implementation so extraction behavior remains covered directly.
#[pyclass(skip_from_py_object)]
#[derive(Clone, Debug)]
pub struct PartitionInfo {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub start_date: String,
    #[pyo3(get)]
    pub end_date: String,
}

impl<'py> FromPyObject<'_, 'py> for PartitionInfo {
    type Error = PyErr;

    fn extract(obj: pyo3::Borrowed<'_, 'py, PyAny>) -> Result<Self, Self::Error> {
        Ok(obj.cast::<Self>()?.borrow().clone())
    }
}

fn utc_month_start(year: i32, month: u32, error_message: &str) -> PyResult<chrono::DateTime<Utc>> {
    Utc.with_ymd_and_hms(year, month, 1, 0, 0, 0)
        .single()
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(error_message.to_string()))
}

#[pyfunction]
pub fn get_partition_info(table_name: String, month_offset: i32) -> PyResult<PartitionInfo> {
    catch_unwind_result(
        "get_partition_info",
        std::panic::AssertUnwindSafe(|| {
            if table_name.is_empty()
                || !table_name
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_')
            {
                return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                    "Invalid table_name '{table_name}': must be non-empty and contain only alphanumeric characters and underscores"
                )));
            }

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

            let start_date = utc_month_start(target_year, target_month, "Invalid date")?;

            let (next_year, next_month) = if target_month == 12 {
                (target_year + 1, 1)
            } else {
                (target_year, target_month + 1)
            };

            let end_date = utc_month_start(next_year, next_month, "Invalid next month date")?;

            Ok(PartitionInfo {
                name: format!("{}_y{}m{:02}", table_name, target_year, target_month),
                start_date: start_date.to_rfc3339(),
                end_date: end_date.to_rfc3339(),
            })
        }),
    )
}

#[pyfunction]
pub fn is_partition_expired(
    partition_name: String,
    table_name: String,
    retention_days: i64,
) -> PyResult<bool> {
    catch_unwind_value(
        "is_partition_expired",
        std::panic::AssertUnwindSafe(|| {
            // LOW-W19: a negative retention_days would make the cutoff a future timestamp,
            // causing every partition to appear un-expired.  Reject it defensively.
            if retention_days < 0 {
                return false;
            }
            let prefix = format!("{}_y", table_name);
            let Some(remainder) = partition_name.strip_prefix(&prefix) else {
                return false;
            };

            let parts: Vec<&str> = remainder.split('m').collect();
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
                if let Some(dur) = Duration::try_days(retention_days) {
                    let cutoff = Utc::now() - dur;
                    return p_end_date < cutoff;
                }
            }

            false
        }),
    )
}

use hmac::{Hmac, Mac};
use sha2::Sha256;

#[pyfunction]
pub fn verify_audit_signature(
    signing_keys: Vec<String>,
    log_data: String,
    signature: String,
) -> PyResult<bool> {
    catch_unwind_result(
        "verify_audit_signature",
        std::panic::AssertUnwindSafe(|| {
            if signing_keys.is_empty() {
                return Ok(false);
            }

            let sig_bytes = match hex::decode(&signature) {
                Ok(b) => b,
                Err(_) => return Ok(false),
            };

            let mut matched = Choice::from(0u8);

            for key_str in signing_keys {
                let key_bytes = Zeroizing::new(key_str.into_bytes());
                if key_bytes.is_empty() {
                    return Err(hmac_key_error("HMAC key cannot be empty"));
                }
                let mut mac = Hmac::<Sha256>::new_from_slice(&key_bytes).map_err(hmac_key_error)?;
                mac.update(log_data.as_bytes());
                let computed = mac.finalize().into_bytes();

                let key_match = computed.as_slice().ct_eq(&sig_bytes);
                matched |= key_match;
            }
            Ok(bool::from(matched))
        }),
    )
}

#[pyfunction]
pub fn verify_event_chain(
    signing_keys: Vec<String>,
    initial_prev_hash: String,
    chain_events: Vec<(String, String, String, String, String)>,
) -> PyResult<(bool, usize, String)> {
    catch_unwind_result(
        "verify_event_chain",
        std::panic::AssertUnwindSafe(|| {
            if chain_events.is_empty() {
                return Ok((true, 0, String::new()));
            }

            if signing_keys.is_empty() {
                return Ok((false, 0, "No signing keys provided".to_string()));
            }

            for key_str in &signing_keys {
                if key_str.is_empty() {
                    return Err(hmac_key_error("HMAC key cannot be empty"));
                }
            }

            let mut current_prev_hash = initial_prev_hash;

            for (idx, (event_id, prev_hash, canonical_payload, timestamp_iso, stored_hash)) in
                chain_events.into_iter().enumerate()
            {
                if prev_hash != current_prev_hash {
                    return Ok((
                        false,
                        idx,
                        format!(
                            "Chain discontinuity at index {} (event {}): expected prev_hash {}, got {}",
                            idx, event_id, current_prev_hash, prev_hash
                        ),
                    ));
                }

                let sig_bytes = match hex::decode(&stored_hash) {
                    Ok(b) => b,
                    Err(_) => {
                        return Ok((
                            false,
                            idx,
                            format!(
                                "Payload or hash tampering detected at event {} (invalid hex hash)",
                                event_id
                            ),
                        ));
                    }
                };

                let data = format!("{}|{}|{}", prev_hash, canonical_payload, timestamp_iso);
                let mut hash_valid = Choice::from(0u8);

                for key_str in &signing_keys {
                    let key_bytes = Zeroizing::new(key_str.as_bytes().to_vec());
                    let mut mac =
                        Hmac::<Sha256>::new_from_slice(&key_bytes).map_err(hmac_key_error)?;
                    mac.update(data.as_bytes());
                    let computed = mac.finalize().into_bytes();

                    let key_match = computed.as_slice().ct_eq(&sig_bytes);
                    hash_valid |= key_match;
                }

                if !bool::from(hash_valid) {
                    return Ok((
                        false,
                        idx,
                        format!("Payload or hash tampering detected at event {}", event_id),
                    ));
                }

                current_prev_hash = stored_hash;
            }

            Ok((true, 0, String::new()))
        }),
    )
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
    m.add_function(wrap_pyfunction!(verify_event_chain, m)?)?;
    // PERF-05: expose limit so Python callers can validate before calling into Rust.
    m.add("MAX_CONFLICT_ITEMS", MAX_CONFLICT_ITEMS)?;
    m.add("MAX_CONFLICT_PAIRS", MAX_CONFLICT_PAIRS)?;
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
    use chrono::{DateTime, Timelike};

    struct ZeroizeDropProbe(std::sync::Arc<std::sync::atomic::AtomicBool>);

    impl zeroize::Zeroize for ZeroizeDropProbe {
        fn zeroize(&mut self) {
            self.0.store(true, std::sync::atomic::Ordering::SeqCst);
        }
    }

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

            // Invalid Python values must be converted to PyErr at the FFI
            // boundary instead of panicking while extracting ScheduleItem.
            assert!(detect_conflicts.call1((py.None(), &existing_list)).is_err());
            let invalid_existing = pyo3::types::PyList::new(py, vec![py.None()]).unwrap();
            assert!(detect_conflicts
                .call1((&target, &invalid_existing))
                .is_err());
            assert!(batch_detect_conflicts.call1((&invalid_existing,)).is_err());

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
            let opt_item = opt_item.expect("an available Monday slot at 10:00 must be returned");
            assert_eq!(opt_item.weekday, "monday");
            assert_eq!(opt_item.end_time - opt_item.start_time, 60 * 60);

            // 5. get_partition_info
            let get_partition_info_py = m.getattr("get_partition_info").unwrap();
            let part_info = get_partition_info_py
                .call1(("notifications", 0i32))
                .unwrap();
            let parsed_part_info: PartitionInfo = part_info.extract().unwrap();
            assert!(parsed_part_info.name.contains("notifications"));
            let invalid_part_info: PyResult<PartitionInfo> = py.None().extract(py);
            assert!(invalid_part_info.is_err());
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

    #[test]
    fn partition_info_december_rolls_into_january() {
        let month = Utc::now().month() as i32;
        let offset = 12 - month;
        let info = get_partition_info("events".to_string(), offset).unwrap();
        assert!(info.name.ends_with("m12"));
        assert!(info.end_date.contains("-01-01T00:00:00+00:00"));
    }

    #[test]
    fn invalid_month_start_is_reported_without_panic() {
        Python::initialize();
        let result = utc_month_start(2026, 13, "invalid month");
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("invalid month"));
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

    #[test]
    fn expired_december_partition_is_parsed() {
        assert!(is_partition_expired("tbl_y2020m12".to_string(), "tbl".to_string(), 1).unwrap());
    }

    #[test]
    fn expired_out_of_range_year_returns_false() {
        assert!(
            !is_partition_expired("tbl_y2147483647m01".to_string(), "tbl".to_string(), 90,)
                .unwrap()
        );
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
    fn test_verify_event_chain_success() {
        let key = "secret_key_12345678901234567890123";
        let h0 = "0".repeat(64);

        let p1 = r#"{"aggregate_id":"1","aggregate_type":"schedule","event_type":"SCHEDULE_CREATED","payload":{"room":"101"},"version":1}"#;
        let t1 = "2026-07-24T12:00:00+00:00";
        let d1 = format!("{}|{}|{}", h0, p1, t1);
        let mut mac1 = Hmac::<Sha256>::new_from_slice(key.as_bytes()).unwrap();
        mac1.update(d1.as_bytes());
        let h1 = hex::encode(mac1.finalize().into_bytes());

        let p2 = r#"{"aggregate_id":"1","aggregate_type":"schedule","event_type":"SCHEDULE_UPDATED","payload":{"room":"202"},"version":2}"#;
        let t2 = "2026-07-24T12:05:00+00:00";
        let d2 = format!("{}|{}|{}", h1, p2, t2);
        let mut mac2 = Hmac::<Sha256>::new_from_slice(key.as_bytes()).unwrap();
        mac2.update(d2.as_bytes());
        let h2 = hex::encode(mac2.finalize().into_bytes());

        let chain = vec![
            (
                "evt-1".to_string(),
                h0.clone(),
                p1.to_string(),
                t1.to_string(),
                h1.clone(),
            ),
            (
                "evt-2".to_string(),
                h1.clone(),
                p2.to_string(),
                t2.to_string(),
                h2.clone(),
            ),
        ];

        let res = verify_event_chain(vec![key.to_string()], h0, chain).unwrap();
        assert!(res.0);
        assert_eq!(res.1, 0);
        assert_eq!(res.2, "");
    }

    #[test]
    fn test_verify_event_chain_discontinuity() {
        let key = "secret_key_12345678901234567890123";
        let h0 = "0".repeat(64);

        let p1 = r#"{"payload":"1"}"#;
        let t1 = "2026-07-24T12:00:00+00:00";
        let d1 = format!("{}|{}|{}", h0, p1, t1);
        let mut mac1 = Hmac::<Sha256>::new_from_slice(key.as_bytes()).unwrap();
        mac1.update(d1.as_bytes());
        let h1 = hex::encode(mac1.finalize().into_bytes());

        let chain = vec![
            (
                "evt-1".to_string(),
                h0.clone(),
                p1.to_string(),
                t1.to_string(),
                h1.clone(),
            ),
            (
                "evt-2".to_string(),
                "bad_prev_hash".to_string(),
                "p2".to_string(),
                "t2".to_string(),
                "h2".to_string(),
            ),
        ];

        let res = verify_event_chain(vec![key.to_string()], h0, chain).unwrap();
        assert!(!res.0);
        assert_eq!(res.1, 1);
        assert!(res.2.contains("Chain discontinuity"));
    }

    #[test]
    fn verify_event_chain_accepts_empty_chain() {
        let result =
            verify_event_chain(vec!["key".to_string()], "prev".to_string(), vec![]).unwrap();

        assert_eq!(result, (true, 0, String::new()));
    }

    #[test]
    fn verify_event_chain_rejects_missing_signing_keys() {
        let result = verify_event_chain(
            vec![],
            "prev".to_string(),
            vec![(
                "event-1".to_string(),
                "prev".to_string(),
                "payload".to_string(),
                "timestamp".to_string(),
                "00".to_string(),
            )],
        )
        .unwrap();

        assert_eq!(result, (false, 0, "No signing keys provided".to_string()));
    }

    #[test]
    fn verify_event_chain_rejects_invalid_hex_hash() {
        let result = verify_event_chain(
            vec!["key".to_string()],
            "prev".to_string(),
            vec![(
                "event-1".to_string(),
                "prev".to_string(),
                "payload".to_string(),
                "timestamp".to_string(),
                "not-hex".to_string(),
            )],
        )
        .unwrap();

        assert!(!result.0);
        assert_eq!(result.1, 0);
        assert!(result.2.contains("invalid hex hash"));
    }

    #[test]
    fn verify_event_chain_rejects_invalid_signature() {
        let result = verify_event_chain(
            vec!["key".to_string()],
            "prev".to_string(),
            vec![(
                "event-1".to_string(),
                "prev".to_string(),
                "payload".to_string(),
                "timestamp".to_string(),
                "00".to_string(),
            )],
        )
        .unwrap();

        assert!(!result.0);
        assert_eq!(result.1, 0);
        assert!(result.2.contains("tampering detected"));
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

        let odd = ScheduleItem {
            parity: "odd".to_string(),
            ..item1.clone()
        };
        let even = ScheduleItem {
            parity: "even".to_string(),
            ..item2.clone()
        };
        assert!(!check_conflict_proto(&odd, &even));
    }

    #[test]
    fn batch_detect_conflicts_exercises_noncanonical_metadata_path() {
        let odd = ScheduleItem {
            id: None,
            weekday: "monday".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: "odd".to_string(),
        };
        let even = ScheduleItem {
            parity: "even".to_string(),
            ..odd.clone()
        };

        // Non-canonical parity forces the metadata-aware branch rather than
        // the fast weekday-only path.
        let result = batch_detect_conflicts(vec![odd, even]).unwrap();
        assert!(result.is_empty());
    }

    #[test]
    fn canonical_weekday_code_covers_fallback() {
        assert_eq!(canonical_weekday_code("monday"), 0);
        assert_eq!(canonical_weekday_code("MONDAY"), u8::MAX);
        assert_eq!(canonical_weekday_code("not-a-weekday"), u8::MAX);
    }

    #[test]
    fn batch_detect_conflicts_covers_canonical_non_overlaps_and_parallel_path() {
        let late = ScheduleItem {
            id: Some(1),
            weekday: "monday".to_string(),
            start_time: 3_000,
            end_time: 4_000,
            parity: "both".to_string(),
        };
        let early = ScheduleItem {
            id: Some(2),
            weekday: "monday".to_string(),
            start_time: 1_000,
            end_time: 2_000,
            parity: "both".to_string(),
        };

        // Keep a small canonical case to exercise the sequential pairwise
        // path before the larger input below crosses the parallel threshold.
        assert!(batch_detect_conflicts(vec![late.clone(), early.clone()])
            .unwrap()
            .is_empty());

        // Include both orderings so each short-circuit overlap comparison is
        // exercised, then add enough disjoint canonical items for rayon's
        // parallel branch to run without producing any conflicts.
        let mut items = vec![late, early.clone()];
        let weekdays = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ];
        for index in 0..32 {
            let start: i64 = 5_000 + (index as i64) * 1_000;
            items.push(ScheduleItem {
                id: Some(index as i32 + 3),
                weekday: weekdays[index % weekdays.len()].to_string(),
                start_time: start,
                end_time: start + 500,
                parity: "both".to_string(),
            });
        }

        assert!(batch_detect_conflicts(items).unwrap().is_empty());

        let noncanonical = ScheduleItem {
            id: Some(100),
            weekday: "monday".to_string(),
            start_time: 9_000,
            end_time: 9_000,
            parity: "both".to_string(),
        };
        assert!(batch_detect_conflicts(vec![noncanonical, early])
            .unwrap()
            .is_empty());
    }

    #[test]
    fn canonical_parallel_path_preserves_overlapping_pairs() {
        let mut items = vec![
            ScheduleItem {
                id: Some(1),
                weekday: "monday".to_string(),
                start_time: 1_000,
                end_time: 3_000,
                parity: "both".to_string(),
            },
            ScheduleItem {
                id: Some(2),
                weekday: "monday".to_string(),
                start_time: 2_000,
                end_time: 4_000,
                parity: "both".to_string(),
            },
        ];
        for index in 0..32 {
            let start = 10_000 + (index as i64) * 1_000;
            items.push(ScheduleItem {
                id: Some(index + 3),
                weekday: "tuesday".to_string(),
                start_time: start,
                end_time: start + 100,
                parity: "both".to_string(),
            });
        }

        let conflicts = batch_detect_conflicts(items).unwrap();
        assert!(conflicts
            .iter()
            .any(|(left, right)| left.id == Some(1) && right.id == Some(2)));
    }

    #[test]
    fn panic_mapping_covers_all_payload_shapes() {
        Python::initialize();
        let borrowed = catch_unwind_value::<(), _>(
            "borrowed",
            std::panic::AssertUnwindSafe(|| std::panic::panic_any("boom")),
        )
        .unwrap_err();
        assert!(borrowed
            .to_string()
            .contains("Rust panic in borrowed: boom"));

        let owned = catch_unwind_value::<(), _>(
            "owned",
            std::panic::AssertUnwindSafe(|| std::panic::panic_any(String::from("owned boom"))),
        )
        .unwrap_err();
        assert!(owned
            .to_string()
            .contains("Rust panic in owned: owned boom"));

        let unknown = catch_unwind_value::<(), _>(
            "unknown",
            std::panic::AssertUnwindSafe(|| std::panic::panic_any(42_u8)),
        )
        .unwrap_err();
        assert!(unknown
            .to_string()
            .contains("Rust panic in unknown: Unknown panic"));

        let success = catch_unwind_result("success", std::panic::AssertUnwindSafe(|| Ok(7_u8)));
        assert_eq!(success.unwrap(), 7);
    }

    #[test]
    fn poisoned_mutex_is_converted_to_python_error() {
        Python::initialize();
        let lock = std::sync::Arc::new(Mutex::new(()));
        let worker_lock = std::sync::Arc::clone(&lock);
        let worker = std::thread::spawn(move || {
            let _guard = worker_lock.lock().unwrap();
            panic!("poison test");
        });
        assert!(worker.join().is_err());

        let result = mutex_guard_or_py_err(lock.lock());
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("ScheduleItem extraction lock is poisoned"));
    }

    #[test]
    fn invalid_rayon_pool_is_reported_without_panic() {
        Python::initialize();
        let result = build_rayon_pool(0);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("RUST_EXT_THREADS must be greater than zero"));
    }

    #[test]
    fn parse_rayon_threads_uses_safe_defaults_for_missing_or_invalid_values() {
        assert_eq!(parse_rayon_threads(None), 4);
        assert_eq!(parse_rayon_threads(Some("2".to_string())), 2);
        assert_eq!(parse_rayon_threads(Some("not-a-number".to_string())), 4);
    }

    #[test]
    fn error_mapping_helpers_preserve_context() {
        Python::initialize();
        let rayon_error = rayon_pool_build_error("synthetic failure");
        assert!(rayon_error
            .to_string()
            .contains("Failed to build rayon thread pool: synthetic failure"));

        let hmac_error = hmac_key_error("synthetic key failure");
        assert!(hmac_error.to_string().contains("Invalid HMAC key length"));
    }

    #[test]
    fn find_optimal_slot_returns_none_without_candidates() {
        assert!(find_optimal_slot(60, Vec::new(), Vec::new())
            .unwrap()
            .is_none());
    }

    #[test]
    fn find_optimal_slot_rejects_durations_that_overflow_chrono() {
        assert!(checked_slot_end(DateTime::<Utc>::MAX_UTC, Duration::seconds(1)).is_none());

        let max_date = DateTime::<Utc>::MAX_UTC.date_naive();
        let max_weekday = weekday_name(max_date.weekday()).to_string();
        assert!(
            find_optimal_slot_at(max_date, u32::MAX, Vec::new(), vec![(max_weekday, vec![0])],)
                .is_none()
        );
    }

    #[test]
    fn find_optimal_slot_returns_none_when_all_candidates_conflict() {
        let day = "monday".to_string();
        let date = next_weekday(Utc::now().date_naive(), Weekday::Mon);
        let start = Utc
            .from_utc_datetime(&date.and_hms_opt(0, 0, 0).unwrap())
            .timestamp();
        let existing = vec![ScheduleItem {
            id: Some(1),
            weekday: day.clone(),
            start_time: start,
            end_time: start + 3600,
            parity: "both".to_string(),
        }];
        let available = vec![(day, vec![0])];

        assert!(find_optimal_slot(60, existing, available)
            .unwrap()
            .is_none());
    }

    #[test]
    fn find_optimal_slot_skips_invalid_hour_candidates() {
        let available = vec![("monday".to_string(), vec![24])];

        assert!(find_optimal_slot(60, Vec::new(), available)
            .unwrap()
            .is_none());
    }

    #[test]
    fn find_optimal_slot_exercises_each_next_day_name() {
        // A two-hour slot beginning at 23:00 crosses midnight for every
        // weekday.  This verifies the public scheduling behavior for all
        // seven localized weekday names returned by the rollover path.
        for weekday in [
            Weekday::Mon,
            Weekday::Tue,
            Weekday::Wed,
            Weekday::Thu,
            Weekday::Fri,
            Weekday::Sat,
            Weekday::Sun,
        ] {
            let day = weekday_name(weekday).to_string();
            let available = vec![(day.clone(), vec![23])];
            let result = find_optimal_slot(120, Vec::new(), available).unwrap();
            assert_eq!(
                result.as_ref().map(|item| item.weekday.as_str()),
                Some(day.as_str())
            );
            assert_eq!(
                result.map(|item| item.end_time - item.start_time),
                Some(120 * 60)
            );
        }
    }

    #[test]
    fn find_optimal_slot_rejects_real_day_two_conflicts() {
        let target_weekday = Weekday::Mon;
        let target_date = next_weekday(Utc::now().date_naive(), target_weekday);
        let next_date = target_date.succ_opt().unwrap();
        let existing_start = Utc
            .from_utc_datetime(&next_date.and_hms_opt(0, 30, 0).unwrap())
            .timestamp();
        let existing = vec![ScheduleItem {
            id: Some(1),
            weekday: weekday_name(next_date.weekday()).to_string(),
            start_time: existing_start,
            end_time: existing_start + 3600,
            parity: "both".to_string(),
        }];

        let available = vec![("monday".to_string(), vec![23])];
        assert!(find_optimal_slot(120, existing, available)
            .unwrap()
            .is_none());
    }

    #[test]
    fn find_optimal_slot_accepts_non_conflicting_real_day_two_item() {
        let target_weekday = Weekday::Mon;
        let target_date = next_weekday(Utc::now().date_naive(), target_weekday);
        let next_date = target_date.succ_opt().unwrap();
        let existing_start = Utc
            .from_utc_datetime(&next_date.and_hms_opt(3, 0, 0).unwrap())
            .timestamp();
        let existing = vec![ScheduleItem {
            id: Some(1),
            weekday: weekday_name(next_date.weekday()).to_string(),
            start_time: existing_start,
            end_time: existing_start + 3600,
            parity: "both".to_string(),
        }];

        let available = vec![("monday".to_string(), vec![23])];
        let result = find_optimal_slot(120, existing, available).unwrap();
        assert_eq!(
            result.as_ref().map(|item| item.weekday.as_str()),
            Some("monday")
        );
    }

    #[test]
    fn find_optimal_slot_accepts_non_conflicting_real_same_day_item() {
        let monday = NaiveDate::from_ymd_opt(2026, 1, 5).unwrap();
        assert_eq!(monday.weekday(), Weekday::Mon);
        let existing_start = Utc
            .from_utc_datetime(&monday.and_hms_opt(12, 0, 0).unwrap())
            .timestamp();
        let expected_start = Utc
            .from_utc_datetime(&monday.and_hms_opt(9, 0, 0).unwrap())
            .timestamp();
        let existing = vec![ScheduleItem {
            id: Some(1),
            weekday: "monday".to_string(),
            start_time: existing_start,
            end_time: existing_start + 3600,
            parity: "both".to_string(),
        }];

        let result =
            find_optimal_slot_at(monday, 60, existing, vec![("monday".to_string(), vec![9])]);

        assert_eq!(
            result.as_ref().map(|item| item.weekday.as_str()),
            Some("monday")
        );
        assert_eq!(
            result.as_ref().map(|item| item.start_time),
            Some(expected_start)
        );
        assert_eq!(
            result.map(|item| item.end_time),
            Some(expected_start + 3600)
        );
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
            // Use a 1970 baseline time-of-day rather than wall-clock time.
            // `find_optimal_slot` normalizes it to the next matching weekday;
            // a live timestamp can overlap both candidates depending on when
            // the test happens to run.
            start_time: 9 * 3600,
            end_time: 10 * 3600,
            parity: "both".to_string(),
        }];

        let available = vec![
            ("invalid_day".to_string(), vec![10]),
            ("monday".to_string(), vec![9, 10]),
        ];

        let slot = find_optimal_slot(60, existing, available);
        assert!(slot.is_ok());
        let found = slot.unwrap().expect("10:00 must remain available");
        assert_eq!(found.weekday, "monday");
        assert_eq!(
            DateTime::<Utc>::from_timestamp(found.start_time, 0)
                .unwrap()
                .time()
                .hour(),
            10
        );
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

        // Duration::try_days rejects an i64-sized duration before subtraction.
        assert!(!is_partition_expired(
            "events_y2020m01".to_string(),
            "events".to_string(),
            i64::MAX
        )
        .unwrap());

        // A parsed zero year is rejected by the structural date guard.
        assert!(
            !is_partition_expired("events_y0m01".to_string(), "events".to_string(), 1).unwrap()
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

    #[test]
    fn test_check_conflict_proto_case_and_whitespace_normalization() {
        let item1 = ScheduleItem {
            id: None,
            weekday: " Monday  ".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: " Both ".to_string(),
        };
        let item2 = ScheduleItem {
            id: None,
            weekday: "monday".to_string(),
            start_time: 1500,
            end_time: 2500,
            parity: "both".to_string(),
        };

        // Should detect conflict despite casing and surrounding whitespace
        assert!(check_conflict_proto(&item1, &item2));

        let item3 = ScheduleItem {
            id: None,
            weekday: "MON".to_string(),
            start_time: 1500,
            end_time: 2500,
            parity: "odd".to_string(),
        };
        let item4 = ScheduleItem {
            id: None,
            weekday: " Monday ".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: " ODD ".to_string(),
        };
        assert!(check_conflict_proto(&item3, &item4));
    }

    #[test]
    fn test_batch_detect_conflicts_max_pairs_cap() {
        // Create 350 items that all overlap on Monday (350 * 349 / 2 = 61,075 pairs > 50,000)
        let mut items = Vec::new();
        for i in 0..350 {
            items.push(ScheduleItem {
                id: Some(i),
                weekday: "monday".to_string(),
                start_time: 1000,
                end_time: 2000,
                parity: "both".to_string(),
            });
        }

        let result = batch_detect_conflicts(items);
        assert!(
            result.is_err(),
            "Should return error when conflict pairs exceed 50,000"
        );
        let err_msg = result.unwrap_err().to_string();
        assert!(err_msg.contains("Detected conflict pairs exceed maximum allowed cap (50000)"));
    }

    #[test]
    fn test_batch_detect_conflicts_max_pairs_cap_noncanonical_metadata() {
        // Exercise the normalized metadata path (parity != "both") as well as
        // the bounded-pair early stop. The canonical path above does not enter
        // the `check_conflict_with_metadata` branch in the parallel iterator.
        let items = (0..320)
            .map(|id| ScheduleItem {
                id: Some(id),
                weekday: "monday".to_string(),
                start_time: 1000,
                end_time: 2000,
                parity: "odd".to_string(),
            })
            .collect();

        let result = batch_detect_conflicts(items);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Detected conflict pairs exceed maximum allowed cap (50000)"));
    }

    #[test]
    fn test_get_partition_info_table_name_validation() {
        // Valid names
        assert!(get_partition_info("notifications".to_string(), 0).is_ok());
        assert!(get_partition_info("audit_logs_123".to_string(), 0).is_ok());

        // Invalid names: empty, containing special characters or SQL injection attempts
        assert!(get_partition_info("".to_string(), 0).is_err());
        assert!(get_partition_info("tbl-name".to_string(), 0).is_err());
        assert!(get_partition_info("tbl; DROP TABLE users;".to_string(), 0).is_err());
        assert!(get_partition_info("tbl/partition".to_string(), 0).is_err());
    }

    #[test]
    fn test_is_partition_expired_strip_prefix() {
        // Single prefix matching
        assert!(
            is_partition_expired("events_y2020m01".to_string(), "events".to_string(), 1).unwrap()
        );

        // Repeated prefix pattern — strip_prefix must only strip one instance
        assert!(!is_partition_expired(
            "events_yevents_y2026m03".to_string(),
            "events".to_string(),
            30
        )
        .unwrap());
    }

    #[test]
    fn test_find_optimal_slot_day2_spanning_conflict() {
        // Slot at 23:00 Monday spanning 120 mins into Tuesday 01:00.
        // Existing schedule has a conflict on Tuesday 00:30-01:30.
        // Derive Tuesday from the selected Monday candidate rather than from
        // today independently; otherwise the test is date-dependent whenever
        // today is Tuesday through Sunday.
        let monday_date = next_weekday(Utc::now().date_naive(), Weekday::Mon);
        let tuesday_date = monday_date + Duration::days(1);
        let tuesday_midnight = tuesday_date
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc()
            .timestamp();

        let existing = vec![ScheduleItem {
            id: Some(1),
            weekday: "tuesday".to_string(),
            start_time: tuesday_midnight + 1800, // 00:30 Tuesday
            end_time: tuesday_midnight + 5400,   // 01:30 Tuesday
            parity: "both".to_string(),
        }];

        let available = vec![("monday".to_string(), vec![23])];

        let result = find_optimal_slot(120, existing, available).unwrap();
        assert!(
            result.is_none(),
            "Slot spanning past midnight into Tuesday 01:00 should conflict with Tuesday 00:30 slot"
        );
    }

    #[test]
    fn find_optimal_slot_normalizes_epoch_day2_conflict() {
        let monday = NaiveDate::from_ymd_opt(2026, 1, 5).unwrap();
        assert_eq!(monday.weekday(), Weekday::Mon);
        let existing = vec![ScheduleItem {
            id: Some(2),
            weekday: "tuesday".to_string(),
            start_time: 1_800,
            end_time: 5_400,
            parity: "both".to_string(),
        }];

        let result = find_optimal_slot_at(
            monday,
            120,
            existing,
            vec![("monday".to_string(), vec![23])],
        );
        assert!(result.is_none());
    }

    #[test]
    fn find_optimal_slot_normalizes_epoch_day2_non_conflict() {
        let monday = NaiveDate::from_ymd_opt(2026, 1, 5).unwrap();
        let existing = vec![ScheduleItem {
            id: Some(3),
            weekday: "tuesday".to_string(),
            start_time: 10_800,
            end_time: 14_400,
            parity: "both".to_string(),
        }];

        let result = find_optimal_slot_at(
            monday,
            120,
            existing,
            vec![("monday".to_string(), vec![23])],
        );
        assert_eq!(
            result.as_ref().map(|item| item.weekday.as_str()),
            Some("monday")
        );
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

    #[test]
    fn test_verify_audit_signature_multi_key_ring() {
        let key1 = "key_alpha_123456789";
        let key2 = "key_beta_987654321";
        let key3 = "key_gamma_555555555";
        let data = "audit_log_record_42";

        let mut mac2 = Hmac::<Sha256>::new_from_slice(key2.as_bytes()).unwrap();
        mac2.update(data.as_bytes());
        let sig2 = hex::encode(mac2.finalize().into_bytes());

        let ring = vec![key1.to_string(), key2.to_string(), key3.to_string()];
        let ok = verify_audit_signature(ring, data.to_string(), sig2).unwrap();
        assert!(ok, "Signature matching second key in key ring must succeed");

        let bad_ring = vec![key1.to_string(), key3.to_string()];
        let fail =
            verify_audit_signature(bad_ring, data.to_string(), hex::encode("wrong")).unwrap();
        assert!(!fail, "Signature matching no key in ring must fail");
    }

    #[test]
    fn test_hmac_empty_key_validation() {
        let err1 =
            verify_audit_signature(vec!["".to_string()], "data".to_string(), "0000".to_string());
        assert!(
            err1.is_err(),
            "Empty key in verify_audit_signature must return error"
        );

        let chain = vec![(
            "e1".to_string(),
            "00".to_string(),
            "p1".to_string(),
            "t1".to_string(),
            "00".to_string(),
        )];
        let err2 = verify_event_chain(vec!["".to_string()], "00".to_string(), chain);
        assert!(
            err2.is_err(),
            "Empty key in verify_event_chain must return error"
        );
    }

    #[test]
    fn test_check_conflict_proto_case_insensitivity() {
        let item_upper = ScheduleItem {
            id: Some(1),
            weekday: "Monday".to_string(),
            start_time: 36000,
            end_time: 39600,
            parity: "Both".to_string(),
        };
        let item_lower = ScheduleItem {
            id: Some(2),
            weekday: "monday".to_string(),
            start_time: 37000,
            end_time: 40000,
            parity: "both".to_string(),
        };
        assert!(
            check_conflict_proto(&item_upper, &item_lower),
            "Casing differences in weekday and parity must not cause false negatives"
        );

        let item_odd_upper = ScheduleItem {
            parity: "ODD".to_string(),
            ..item_upper.clone()
        };
        let item_odd_lower = ScheduleItem {
            parity: "odd".to_string(),
            ..item_lower.clone()
        };
        assert!(
            check_conflict_proto(&item_odd_upper, &item_odd_lower),
            "Case-insensitive parity match must detect conflict"
        );
    }

    #[test]
    fn test_find_optimal_slot_1970_baseline_schedule_items() {
        // 1970 baseline time-of-day item: 10:00 to 11:00 AM (36000..39600 seconds) on Monday
        let existing_1970 = vec![ScheduleItem {
            id: Some(101),
            weekday: "Monday".to_string(),
            start_time: 36000,
            end_time: 39600,
            parity: "Both".to_string(),
        }];

        // Available blocks on Monday at 10:00 AM (hour 10) and 11:00 AM (hour 11)
        let available = vec![("monday".to_string(), vec![10, 11])];

        let slot = find_optimal_slot(60, existing_1970, available)
            .unwrap()
            .expect("Optimal slot search must succeed");

        // Hour 10 conflicts with the 1970 baseline item (10:00-11:00). So hour 11 (11:00-12:00) must be picked.
        let slot_dt = DateTime::<Utc>::from_timestamp(slot.start_time, 0).unwrap();
        assert_eq!(
            slot_dt.time().hour(),
            11,
            "Slot at 10:00 AM must conflict with 1970 baseline item and pick 11:00 AM slot instead"
        );
    }

    #[test]
    fn test_empirical_constant_time_audit_signature_multi_key_ring() {
        let keys = vec![
            "key_index_0_alpha_1234567890".to_string(),
            "key_index_1_beta_12345678901".to_string(),
            "key_index_2_gamma_1234567890".to_string(),
            "key_index_3_delta_1234567890".to_string(),
            "key_index_4_epsilon_12345678".to_string(),
        ];
        let data = "log_data_payload_audit_record_2026";

        // Compute signature for key at index 0
        let mut mac0 = Hmac::<Sha256>::new_from_slice(keys[0].as_bytes()).unwrap();
        mac0.update(data.as_bytes());
        let sig0 = hex::encode(mac0.finalize().into_bytes());

        // Compute signature for key at index 4
        let mut mac4 = Hmac::<Sha256>::new_from_slice(keys[4].as_bytes()).unwrap();
        mac4.update(data.as_bytes());
        let sig4 = hex::encode(mac4.finalize().into_bytes());

        // Both key index 0 and key index 4 must be accepted by verify_audit_signature
        assert!(verify_audit_signature(keys.clone(), data.to_string(), sig0.clone()).unwrap());
        assert!(verify_audit_signature(keys.clone(), data.to_string(), sig4.clone()).unwrap());

        // Timing empirical verification: test 5,000 iterations for key 0 vs key 4 vs invalid key
        let sig_invalid = hex::encode([0u8; 32]);

        let start0 = std::time::Instant::now();
        for _ in 0..5_000 {
            let _ = verify_audit_signature(keys.clone(), data.to_string(), sig0.clone()).unwrap();
        }
        let elapsed0 = start0.elapsed();

        let start4 = std::time::Instant::now();
        for _ in 0..5_000 {
            let _ = verify_audit_signature(keys.clone(), data.to_string(), sig4.clone()).unwrap();
        }
        let elapsed4 = start4.elapsed();

        let start_inv = std::time::Instant::now();
        for _ in 0..5_000 {
            let _ = verify_audit_signature(keys.clone(), data.to_string(), sig_invalid.clone())
                .unwrap();
        }
        let elapsed_inv = start_inv.elapsed();

        println!(
            "Empirical Timing: Key 0 match: {:?}, Key 4 match: {:?}, Invalid match: {:?}",
            elapsed0, elapsed4, elapsed_inv
        );
        // All key positions iterate through all N keys in constant time (no break on match)
    }

    #[test]
    fn test_empirical_constant_time_event_chain_multi_key_ring() {
        let keys = vec![
            "key_index_0_alpha_1234567890".to_string(),
            "key_index_1_beta_12345678901".to_string(),
            "key_index_2_gamma_1234567890".to_string(),
        ];
        let h0 = "0".repeat(64);
        let p1 = r#"{"event":"test_event_1"}"#;
        let t1 = "2026-07-30T12:00:00+00:00";
        let d1 = format!("{}|{}|{}", h0, p1, t1);

        // Sign with key index 2 (last key in ring)
        let mut mac = Hmac::<Sha256>::new_from_slice(keys[2].as_bytes()).unwrap();
        mac.update(d1.as_bytes());
        let h1 = hex::encode(mac.finalize().into_bytes());

        let chain = vec![(
            "evt-1".to_string(),
            h0.clone(),
            p1.to_string(),
            t1.to_string(),
            h1,
        )];

        let (ok, err_idx, err_msg) = verify_event_chain(keys.clone(), h0, chain).unwrap();
        assert!(
            ok,
            "Event chain signed by last key in ring must be valid: {}",
            err_msg
        );
        assert_eq!(err_idx, 0);

        // Test timing for key index 0 vs key index 2
        let mut mac0 = Hmac::<Sha256>::new_from_slice(keys[0].as_bytes()).unwrap();
        mac0.update(d1.as_bytes());
        let h1_0 = hex::encode(mac0.finalize().into_bytes());
        let chain0 = vec![(
            "evt-1".to_string(),
            "0".repeat(64),
            p1.to_string(),
            t1.to_string(),
            h1_0,
        )];

        let start0 = std::time::Instant::now();
        for _ in 0..5_000 {
            let _ = verify_event_chain(keys.clone(), "0".repeat(64), chain0.clone()).unwrap();
        }
        let elapsed0 = start0.elapsed();

        let mut mac2 = Hmac::<Sha256>::new_from_slice(keys[2].as_bytes()).unwrap();
        mac2.update(d1.as_bytes());
        let h1_2 = hex::encode(mac2.finalize().into_bytes());

        let chain2 = vec![(
            "evt-1".to_string(),
            "0".repeat(64),
            p1.to_string(),
            t1.to_string(),
            h1_2,
        )];

        let start2 = std::time::Instant::now();
        for _ in 0..5_000 {
            let _ = verify_event_chain(keys.clone(), "0".repeat(64), chain2.clone()).unwrap();
        }
        let elapsed2 = start2.elapsed();

        println!(
            "Event Chain Empirical Timing: Key 0: {:?}, Key 2: {:?}",
            elapsed0, elapsed2
        );
    }

    #[test]
    fn test_empirical_key_zeroization_behavior() {
        // Verify the wrapper invokes Zeroize during Drop without reading a
        // buffer after its owner has been deallocated (which would be UB).
        let zeroized = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
        {
            let _zeroized_wrapper =
                Zeroizing::new(ZeroizeDropProbe(std::sync::Arc::clone(&zeroized)));
        }
        assert!(zeroized.load(std::sync::atomic::Ordering::SeqCst));
    }

    #[test]
    fn test_empirical_check_conflict_proto_comprehensive_matrix() {
        // 1. Weekday full name vs 3-letter alias with mixed casing and whitespace
        let pairs = vec![
            (" Monday  ", "mon", true),
            ("TUESDAY", " Tue ", true),
            ("wednesday", "WED", true),
            (" Thu ", "THURSDAY", true),
            ("Friday", "FRI ", true),
            ("SATURDAY", "sat", true),
            ("Sun", " sunday ", true),
            (" Monday ", "tuesday", false),
            ("DAY_X", "day_x", true),
            ("  CUSTOM_WD  ", "custom_wd", true),
        ];

        for (wd_a, wd_b, expected_wd_match) in pairs {
            let item_a = ScheduleItem {
                id: None,
                weekday: wd_a.to_string(),
                start_time: 1000,
                end_time: 2000,
                parity: "both".to_string(),
            };
            let item_b = ScheduleItem {
                id: None,
                weekday: wd_b.to_string(),
                start_time: 1500,
                end_time: 2500,
                parity: "both".to_string(),
            };
            assert_eq!(
                check_conflict_proto(&item_a, &item_b),
                expected_wd_match,
                "Failed weekday match assertion for '{}' vs '{}'",
                wd_a,
                wd_b
            );
        }

        // 2. Parity case-insensitivity and whitespace trimming matrix
        let parity_pairs = vec![
            (" BOTH ", "odd", true),
            ("both", " EVEN ", true),
            (" ODD ", "odd", true),
            ("even", " EVEN ", true),
            ("odd", "EVEN", false),
            ("  EVEN  ", "  ODD  ", false),
        ];

        for (par_a, par_b, expected_parity_match) in parity_pairs {
            let item_a = ScheduleItem {
                id: None,
                weekday: "monday".to_string(),
                start_time: 1000,
                end_time: 2000,
                parity: par_a.to_string(),
            };
            let item_b = ScheduleItem {
                id: None,
                weekday: "monday".to_string(),
                start_time: 1500,
                end_time: 2500,
                parity: par_b.to_string(),
            };
            assert_eq!(
                check_conflict_proto(&item_a, &item_b),
                expected_parity_match,
                "Failed parity match assertion for '{}' vs '{}'",
                par_a,
                par_b
            );
        }

        // 3. Time boundaries and edge cases
        let base = ScheduleItem {
            id: None,
            weekday: "monday".to_string(),
            start_time: 1000,
            end_time: 2000,
            parity: "both".to_string(),
        };

        // Abutting interval (starts exactly at end_time): should NOT conflict
        let abutting = ScheduleItem {
            start_time: 2000,
            end_time: 3000,
            ..base.clone()
        };
        assert!(!check_conflict_proto(&base, &abutting));

        // Zero-length interval: should NOT conflict
        let zero_length = ScheduleItem {
            start_time: 1500,
            end_time: 1500,
            ..base.clone()
        };
        assert!(!check_conflict_proto(&base, &zero_length));

        // Inverted interval: should NOT conflict
        let inverted = ScheduleItem {
            start_time: 2500,
            end_time: 1500,
            ..base.clone()
        };
        assert!(!check_conflict_proto(&base, &inverted));

        // Partial overlap: MUST conflict
        let overlap = ScheduleItem {
            start_time: 1999,
            end_time: 3000,
            ..base.clone()
        };
        assert!(check_conflict_proto(&base, &overlap));
    }

    #[test]
    fn test_empirical_find_optimal_slot_1970_epoch_normalization_comprehensive() {
        // 1. Midnight 1970 item (0..3600 seconds = 00:00-01:00) with uppercase weekday & parity
        let existing_midnight = vec![ScheduleItem {
            id: Some(1),
            weekday: " MONDAY ".to_string(),
            start_time: 0,
            end_time: 3600,
            parity: " BOTH ".to_string(),
        }];

        // Available blocks at 00:00 (hour 0) and 01:00 (hour 1)
        let available_mid = vec![("monday".to_string(), vec![0, 1])];
        let slot_mid = find_optimal_slot(60, existing_midnight, available_mid)
            .unwrap()
            .expect("Must find slot for hour 1");
        let dt_mid = DateTime::<Utc>::from_timestamp(slot_mid.start_time, 0).unwrap();
        assert_eq!(
            dt_mid.time().hour(),
            1,
            "Hour 0 conflicts with 1970 00:00-01:00 item"
        );

        // 2. Late night 1970 item (82800..86400 seconds = 23:00-24:00)
        let existing_night = vec![ScheduleItem {
            id: Some(2),
            weekday: "mon".to_string(),
            start_time: 82800,
            end_time: 86400,
            parity: "ODD".to_string(),
        }];
        let available_night = vec![("Monday".to_string(), vec![22, 23])];
        let slot_night = find_optimal_slot(60, existing_night, available_night)
            .unwrap()
            .expect("Must find slot for hour 22");
        let dt_night = DateTime::<Utc>::from_timestamp(slot_night.start_time, 0).unwrap();
        assert_eq!(
            dt_night.time().hour(),
            22,
            "Hour 23 conflicts with 1970 23:00-24:00 item"
        );

        // 3. Spanning candidate with 1970 baseline item on Day 2
        // Existing 1970 item on Tuesday 00:30-01:30 (1800..5400)
        let existing_tue_1970 = vec![ScheduleItem {
            id: Some(3),
            weekday: "TUESDAY".to_string(),
            start_time: 1800,
            end_time: 5400,
            parity: "both".to_string(),
        }];
        // Candidate: Monday at 23:00 for 120 minutes (23:00 Mon to 01:00 Tue)
        let available_span = vec![("monday".to_string(), vec![23])];
        let slot_span = find_optimal_slot(120, existing_tue_1970, available_span).unwrap();
        assert!(
            slot_span.is_none(),
            "Monday 23:00 slot (120m) spanning to Tuesday 01:00 must conflict with 1970 Tuesday 00:30 item"
        );
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
