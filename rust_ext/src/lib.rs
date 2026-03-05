use pyo3::prelude::*;
use rayon::prelude::*;
use chrono::{DateTime, Utc, TimeZone, Datelike, Duration};

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

#[pyfunction]
fn batch_detect_conflicts(items: Vec<ScheduleItem>) -> Vec<(ScheduleItem, ScheduleItem)> {
    // Parallelize conflict detection using rayon
    items
        .par_iter()
        .enumerate()
        .flat_map(|(i, a)| {
            items[i + 1..]
                .par_iter()
                .filter(move |b| check_conflict_proto(a, b))
                .map(move |b| (a.clone(), b.clone()))
                .collect::<Vec<_>>()
        })
        .collect()
}

#[pyfunction]
#[pyo3(signature = (duration_minutes, existing_schedule, preferred_weekdays=None))]
fn find_optimal_slot(
    duration_minutes: u32,
    existing_schedule: Vec<ScheduleItem>,
    preferred_weekdays: Option<Vec<String>>,
) -> Option<ScheduleItem> {
    let days = preferred_weekdays.unwrap_or_else(|| {
        vec!["Monday".to_string(), "Tuesday".to_string(), "Wednesday".to_string(), "Thursday".to_string(), "Friday".to_string()]
    });

    for day in days {
        for hour in [9, 11, 13, 15] {
            let now = Utc::now();
            let current_year = now.year();

            // Construct time for the current year
            let start_date_time = Utc.with_ymd_and_hms(current_year, 1, 1, hour, 0, 0).single();
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

/// A Python module implemented in Rust.
#[pymodule]
fn rust_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ScheduleItem>()?;
    m.add_function(wrap_pyfunction!(detect_conflicts, m)?)?;
    m.add_function(wrap_pyfunction!(batch_detect_conflicts, m)?)?;
    m.add_function(wrap_pyfunction!(find_optimal_slot, m)?)?;
    Ok(())
}
