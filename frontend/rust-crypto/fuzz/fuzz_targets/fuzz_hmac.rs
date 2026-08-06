#![no_main]

use libfuzzer_sys::fuzz_target;
use uni_wasm_crypto::hmac_sha256_sign;

fuzz_target!(|data: &[u8]| {
    // The public API accepts text, so preserve malformed-byte cases through
    // UTF-8 replacement instead of silently dropping them from the corpus.
    let input = String::from_utf8_lossy(data);
    let digest = hmac_sha256_sign(input.as_ref(), input.as_ref());
    assert_eq!(digest.len(), 64);
    assert!(digest.bytes().all(|byte| byte.is_ascii_hexdigit()));
});
