#![no_main]

use libfuzzer_sys::fuzz_target;
use wasm_sanitizer::strip_html;

fuzz_target!(|data: &[u8]| {
    if let Ok(input) = std::str::from_utf8(data) {
        let output = strip_html(input);
        assert!(!output.contains('<'));
    }
});
