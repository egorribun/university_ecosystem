#![no_main]

use libfuzzer_sys::fuzz_target;
use uuid::Uuid;

fuzz_target!(|data: &[u8]| {
    if let Ok(s) = std::str::from_utf8(data) {
        // Try parsing string as UUID
        if let Ok(u) = Uuid::parse_str(s) {
            // Check if it is v7
            if u.get_version_num() == 7 {
                // Extract timestamp
                if let Some(t) = u.get_timestamp() {
                    let _seconds = t.to_unix().0;
                }
            }
        }
    }
});
