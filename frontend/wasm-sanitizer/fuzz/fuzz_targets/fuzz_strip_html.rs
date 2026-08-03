#![no_main]

use libfuzzer_sys::fuzz_target;
use wasm_sanitizer::strip_html;

fuzz_target!(|data: &[u8]| {
    // Keep malformed-byte inputs in the fuzz domain; browser text bindings
    // replace invalid UTF-8 before calling the sanitizer.
    let input = String::from_utf8_lossy(data);
    let output = strip_html(input.as_ref());
    assert!(!output.contains('<'));
});
