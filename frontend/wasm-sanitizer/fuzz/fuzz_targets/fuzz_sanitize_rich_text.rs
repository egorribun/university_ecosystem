#![no_main]

use libfuzzer_sys::fuzz_target;
use wasm_sanitizer::sanitize_rich_text;

fuzz_target!(|data: &[u8]| {
    if let Ok(input) = std::str::from_utf8(data) {
        let once = sanitize_rich_text(input);
        assert_eq!(sanitize_rich_text(&once), once);
    }
});
