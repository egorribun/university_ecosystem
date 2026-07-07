#![no_main]

use libfuzzer_sys::fuzz_target;
use pyo3_sanitizer::sanitize_rich_text;

fuzz_target!(|data: &[u8]| {
    if let Ok(s) = std::str::from_utf8(data) {
        let result = sanitize_rich_text(s);
        // Idempotency invariant: sanitizing twice must equal sanitizing once.
        // WHY: any divergence would mean the sanitizer produces output that it
        // considers "dirty", which breaks caching and diffing guarantees.
        let result2 = sanitize_rich_text(&result);
        assert_eq!(result, result2, "sanitize_rich_text is not idempotent");
    }
});
