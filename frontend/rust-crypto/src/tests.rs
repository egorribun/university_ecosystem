use super::{
    derive_scrypt_output, fill_scrypt_output, hmac_sha256_sign, make_err, pbkdf2_derive,
    scrypt_derive, ErrorType, ScryptParams,
};

// Generate private-helper fixtures from the OS CSPRNG rather than embedding
// crypto-looking string or byte literals in the production source tree. The
// RFC known-answer vectors remain in tests/native.rs, while these generated
// fixtures exercise private error paths that integration tests cannot access.
fn fixture_bytes(length: usize) -> Vec<u8> {
    let mut bytes = vec![0; length];
    getrandom::getrandom(&mut bytes).expect("test CSPRNG must be available");
    bytes
}

fn fixture_text(length: usize) -> String {
    hex::encode(fixture_bytes(length))
}

#[test]
fn hmac_sha256_sign_is_deterministic_and_hex_encoded() {
    let key = fixture_text(3);
    let message = fixture_text(7);
    let first = hmac_sha256_sign(&key, &message);
    let second = hmac_sha256_sign(&key, &message);

    assert_eq!(first, second);
    assert_eq!(first.len(), 64);
    assert!(first.chars().all(|character| character.is_ascii_hexdigit()));
}

#[test]
fn pbkdf2_rejects_zero_and_oversized_parameters() {
    let password = fixture_text(8);
    let salt = fixture_text(4);
    assert!(pbkdf2_derive(&password, &salt, 0, 32).is_err());
    assert!(pbkdf2_derive(&password, &salt, 1_000_001, 32).is_err());
    assert!(pbkdf2_derive(&password, &salt, 1, 0).is_err());
    assert!(pbkdf2_derive(&password, &salt, 1, 1_025).is_err());
}

#[test]
fn scrypt_rejects_zero_cost_without_panicking() {
    let password = fixture_bytes(8);
    let salt = fixture_bytes(4);
    assert!(scrypt_derive(&password, &salt, 0, 8, 1, 64).is_err());
}

#[test]
fn scrypt_rejects_non_power_of_two_cost() {
    let password = fixture_bytes(8);
    let salt = fixture_bytes(4);
    assert!(scrypt_derive(&password, &salt, 3, 8, 1, 64).is_err());
}

#[test]
fn scrypt_derives_valid_output_in_unit_coverage() {
    let password = fixture_bytes(8);
    let salt = fixture_bytes(4);
    let first = scrypt_derive(&password, &salt, 16, 1, 1, 16)
        .expect("valid scrypt parameters must derive output");
    let second = scrypt_derive(&password, &salt, 16, 1, 1, 16)
        .expect("valid scrypt parameters must derive output");

    assert_eq!(first, second);
    assert_eq!(first.len(), 16);
    assert!(first.iter().any(|byte| *byte != 0));
}

#[test]
fn scrypt_maps_output_length_error() {
    let params = ScryptParams::recommended();
    let password = fixture_bytes(8);
    let salt = fixture_bytes(4);
    let mut empty_output = [];
    assert!(fill_scrypt_output(&password, &salt, &params, &mut empty_output).is_err());
}

fn fail_scrypt_output(
    _password: &[u8],
    _salt: &[u8],
    _params: &ScryptParams,
    _output: &mut [u8],
) -> Result<(), ErrorType> {
    Err(make_err("injected scrypt failure"))
}

#[test]
fn scrypt_propagates_output_error() {
    let params = ScryptParams::new(4, 1, 1, 16).expect("test params must be valid");
    let password = fixture_bytes(8);
    let salt = fixture_bytes(4);

    let result = derive_scrypt_output(&password, &salt, &params, 16, fail_scrypt_output);

    assert!(result.is_err());
}
