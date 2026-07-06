#![no_main]
use libfuzzer_sys::fuzz_target;

// Fuzz arbitrary byte sequences through conflict detection parsing.
// We test that the parser never panics on any input.
fuzz_target!(|data: &[u8]| {
    if let Ok(s) = std::str::from_utf8(data) {
        // parse_weekday must not panic on any valid UTF-8
        let _ = rust_ext::parse_weekday(s);
    }
});
