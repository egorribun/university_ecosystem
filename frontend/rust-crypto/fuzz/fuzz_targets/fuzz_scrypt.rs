#![no_main]

use libfuzzer_sys::fuzz_target;
use uni_wasm_crypto::scrypt_derive;

fuzz_target!(|data: &[u8]| {
    // Keep fuzz cases bounded and deterministic: only small, valid parameters
    // are allowed to reach the memory-hard primitive. Derive the salt from
    // input instead of embedding a crypto-looking fixture in the fuzz target;
    // fuzz code is not a production secret source.
    let n = 16;
    let r = 1;
    let p = 1;
    let salt = &data[..data.len().min(16)];
    let output =
        scrypt_derive(data, salt, n, r, p, 16).expect("bounded parameters are valid");
    assert_eq!(output.len(), 16);
});
