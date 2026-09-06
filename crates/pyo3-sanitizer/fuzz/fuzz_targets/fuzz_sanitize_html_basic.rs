#![no_main]

use libfuzzer_sys::fuzz_target;

#[path = "../../src/sanitizer.rs"]
mod sanitizer;
use sanitizer::sanitize_html_basic;

fuzz_target!(|data: &[u8]| {
    if let Ok(s) = std::str::from_utf8(data) {
        let result = sanitize_html_basic(s);
        // UTF-8 contract: output must be valid UTF-8 (ammonia guarantees this,
        // but we assert explicitly to catch any regression in the binding layer).
        let _ = std::str::from_utf8(result.as_bytes())
            .expect("sanitize_html_basic output must be valid UTF-8");
        // Idempotency: two passes must equal one pass.
        let result2 = sanitize_html_basic(&result);
        assert_eq!(result, result2, "sanitize_html_basic is not idempotent");
    }
});
