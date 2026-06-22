#![no_main]

use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // Only process valid UTF-8 — all Python strings are UTF-8.
    if let Ok(s) = std::str::from_utf8(data) {
        let _ = pyo3_sanitizer::sanitize_rich_text(s);
        let _ = pyo3_sanitizer::sanitize_html_basic(s);
        let _ = pyo3_sanitizer::strip_html(s);
    }
});
