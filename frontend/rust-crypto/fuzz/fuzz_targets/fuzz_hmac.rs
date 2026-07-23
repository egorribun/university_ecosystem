#![no_main]

use libfuzzer_sys::fuzz_target;
use uni_wasm_crypto::hmac_sha256_sign;

fuzz_target!(|data: &[u8]| {
    if let Ok(input) = std::str::from_utf8(data) {
        let digest = hmac_sha256_sign(input, input);
        assert_eq!(digest.len(), 64);
        assert!(digest.bytes().all(|byte| byte.is_ascii_hexdigit()));
    }
});
