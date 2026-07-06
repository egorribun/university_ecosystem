#![no_main]

use libfuzzer_sys::fuzz_target;
use uuid::Uuid;

fuzz_target!(|data: &[u8]| {
    // 1. Try parsing string as UUID (existing logic)
    if let Ok(s) = std::str::from_utf8(data) {
        if let Ok(u) = Uuid::parse_str(s) {
            if u.get_version_num() == 7 {
                if let Some(t) = u.get_timestamp() {
                    let _seconds = t.to_unix().0;
                }
            }
        }
    }

    // 2. Generate UUID v7 using fuzz bytes as entropy (damaged entropy fuzzing)
    if data.len() >= 16 {
        let mut bytes = [0u8; 16];
        bytes.copy_from_slice(&data[0..16]);

        // Layout of UUID v7:
        // - 48 bits (6 bytes): timestamp
        // - 4 bits: version (0111)
        // - 12 bits: rand_a
        // - 2 bits: variant (10)
        // - 62 bits: rand_b
        // Set version to 7
        bytes[6] = (bytes[6] & 0x0f) | 0x70;
        // Set variant to RFC 4122
        bytes[8] = (bytes[8] & 0x3f) | 0x80;

        let u = Uuid::from_bytes(bytes);
        assert_eq!(u.get_version_num(), 7);
        assert_eq!(u.get_variant(), uuid::Variant::RFC4122);

        if let Some(t) = u.get_timestamp() {
            let _seconds = t.to_unix().0;
        }
    }
});
