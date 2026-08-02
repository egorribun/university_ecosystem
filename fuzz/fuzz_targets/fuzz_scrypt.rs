#![no_main]

use libfuzzer_sys::fuzz_target;
use uni_wasm_crypto::scrypt_derive;

fuzz_target!(|input: &[u8]| {
    if input.len() < 5 {
        return;
    }

    // Keep fuzz cases bounded: the target validates parameter handling while
    // avoiding attacker-controlled memory or CPU amplification in the harness.
    let log_n = 4 + (input[0] % 4);
    let n = 1u32 << log_n;
    let r = 1 + (input[1] % 4) as u32;
    let p = 1 + (input[2] % 2) as u32;
    let dk_len = 1 + (input[3] as usize % 64);
    let split = 4 + (input[4] as usize % (input.len() - 4));
    let password = &input[4..split];
    let salt = &input[split..];

    let derived = scrypt_derive(password, salt, n, r, p, dk_len)
        .expect("bounded valid scrypt parameters must derive successfully");
    assert_eq!(derived.len(), dk_len);
});
