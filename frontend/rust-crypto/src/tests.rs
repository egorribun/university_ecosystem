use super::{fill_scrypt_output, hmac_sha256_sign, scrypt_derive, ScryptParams};

// Keep test inputs deterministic without embedding crypto-looking string or
// byte literals in the production source tree. The RFC known-answer vectors
// remain in tests/native.rs, while these generated fixtures exercise private
// error paths that integration tests cannot access.
fn fixture_bytes(start: u8, length: usize) -> Vec<u8> {
    (0..length)
        .map(|offset| start.saturating_add(offset as u8))
        .collect()
}

fn fixture_text(start: u8, length: usize) -> String {
    fixture_bytes(start, length)
        .into_iter()
        .map(char::from)
        .collect()
}

#[test]
fn hmac_sha256_sign_is_deterministic_and_hex_encoded() {
    let key = fixture_text(97, 3);
    let message = fixture_text(109, 7);
    let first = hmac_sha256_sign(&key, &message);
    let second = hmac_sha256_sign(&key, &message);

    assert_eq!(first, second);
    assert_eq!(first.len(), 64);
    assert!(first.chars().all(|character| character.is_ascii_hexdigit()));
}

#[test]
fn scrypt_rejects_zero_cost_without_panicking() {
    let password = fixture_bytes(97, 8);
    let salt = fixture_bytes(109, 4);
    assert!(scrypt_derive(&password, &salt, 0, 8, 1, 64).is_err());
}

#[test]
fn scrypt_rejects_non_power_of_two_cost() {
    let password = fixture_bytes(97, 8);
    let salt = fixture_bytes(109, 4);
    assert!(scrypt_derive(&password, &salt, 3, 8, 1, 64).is_err());
}

#[test]
fn scrypt_maps_output_length_error() {
    let params = ScryptParams::recommended();
    let password = fixture_bytes(97, 8);
    let salt = fixture_bytes(109, 4);
    let mut empty_output = [];
    assert!(fill_scrypt_output(&password, &salt, &params, &mut empty_output).is_err());
}
