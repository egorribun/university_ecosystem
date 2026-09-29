#![no_main]

use libfuzzer_sys::fuzz_target;
use wasm_sanitizer::sanitize_rich_text;

fuzz_target!(|data: &[u8]| {
    // Do not discard malformed-byte cases: browser text conversion replaces
    // invalid UTF-8 before the WASM sanitizer receives it.
    let input = String::from_utf8_lossy(data);
    let once = sanitize_rich_text(input.as_ref());
    let twice = sanitize_rich_text(&once);
    assert_eq!(once, twice, "sanitize_rich_text is not idempotent");
});
