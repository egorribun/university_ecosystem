#![no_main]

use libfuzzer_sys::fuzz_target;

#[path = "../../src/sanitizer.rs"]
mod sanitizer;
use sanitizer::strip_html;

fuzz_target!(|data: &[u8]| {
    if let Ok(s) = std::str::from_utf8(data) {
        let result = strip_html(s);
        // Zero-HTML contract: strip_html must never emit an opening angle bracket.
        // WHY: any surviving '<' would mean a raw tag delimiter reached indexing
        // or display pipelines downstream — that is the core invariant we guard.
        assert!(
            !result.contains('<'),
            "strip_html output contains '<': {result:?}"
        );
    }
});
