#![cfg(not(target_arch = "wasm32"))]

use proptest::prelude::*;
use uni_wasm_crypto::{hmac_sha256_sign, pbkdf2_derive, scrypt_derive};


// Native Known-Answer-Test (KAT) suite. The #[wasm_bindgen] functions are
// callable as plain Rust on a non-wasm target; PBKDF2/HMAC return hex Strings
// and scrypt returns Ok(Vec<u8>) on valid params. All vectors are canonical RFC
// values; running them against RustCrypto is mutual confirmation.

// RFC 7914 section 11: PBKDF2-HMAC-SHA-256, P="passwd", S="salt", c=1, dkLen=64.
const PBKDF2_PASSWD_SALT_C1: &str = "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc49ca9cccf179b645991664b39d77ef317c71b845b1e30bd509112041d3a19783"; // pragma: allowlist secret

// RFC 4231 section 4.2 (TC1): key = 0x0b x20, data = "Hi There".
const HMAC_TC1: &str = "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"; // pragma: allowlist secret
                                                                                           // RFC 4231 section 4.3 (TC2): key = "Jefe", data = "what do ya want for nothing?".
const HMAC_TC2: &str = "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"; // pragma: allowlist secret

// RFC 7914 section 12: scrypt vectors. Pass the actual N; scrypt_derive takes ilog2.
const SCRYPT_V1: &str = "77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442fcd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906"; // pragma: allowlist secret
const SCRYPT_V2: &str = "fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b3731622eaf30d92e22a3886ff109279d9830dac727afb94a83ee6d8360cbdfa2cc0640"; // pragma: allowlist secret
const SCRYPT_V3: &str = "7023bdcb3afd7348461c06cd81fd38ebfda8fbba904f8e3ea9b543f6545da1f2d5432955613f0fcf62d49705242a9af9e61e85dc0d651e40dfcf017b45575887"; // pragma: allowlist secret

#[test]
fn pbkdf2_hmac_sha256_rfc7914_vector() {
    assert_eq!(
        pbkdf2_derive("passwd", "salt", 1, 64),
        PBKDF2_PASSWD_SALT_C1
    );
}

#[test]
fn pbkdf2_length_tracks_key_size() {
    assert_eq!(pbkdf2_derive("pw", "salt", 2, 20).len(), 40);
}

#[test]
fn hmac_sha256_rfc4231_tc1() {
    let key = "\u{0b}".repeat(20);
    assert_eq!(hmac_sha256_sign(&key, "Hi There"), HMAC_TC1);
}

#[test]
fn hmac_sha256_rfc4231_tc2() {
    assert_eq!(
        hmac_sha256_sign("Jefe", "what do ya want for nothing?"),
        HMAC_TC2
    );
}

#[test]
fn hmac_sha256_is_deterministic() {
    let a = hmac_sha256_sign("k", "m");
    let b = hmac_sha256_sign("k", "m");
    assert_eq!(a, b);
    assert_eq!(a.len(), 64, "SHA-256 HMAC is 32 bytes = 64 hex chars");
}

#[test]
fn scrypt_rfc7914_vector1() {
    let out = scrypt_derive(b"", b"", 16, 1, 1, 64).expect("valid params");
    assert_eq!(hex::encode(out), SCRYPT_V1);
}

#[test]
fn scrypt_rfc7914_vector2() {
    let out = scrypt_derive(b"password", b"NaCl", 1024, 8, 16, 64).expect("valid params");
    assert_eq!(hex::encode(out), SCRYPT_V2);
}

#[test]
fn scrypt_rfc7914_vector3() {
    let out =
        scrypt_derive(b"pleaseletmein", b"SodiumChloride", 16384, 8, 1, 64).expect("valid params");
    assert_eq!(hex::encode(out), SCRYPT_V3);
}

#[test]
fn scrypt_dk_len_is_honored() {
    let out = scrypt_derive(b"pw", b"salt", 16, 1, 1, 32).expect("valid params");
    assert_eq!(out.len(), 32);
}

#[test]
fn hmac_sha256_sign_with_modified_key_fails_verification() {
    let key1 = "my-secure-key";
    let key2 = "my-secure-key-damaged"; // modified key
    let message = "audit-log-payload";

    let sig1 = hmac_sha256_sign(key1, message);
    let sig2 = hmac_sha256_sign(key2, message);

    assert_ne!(
        sig1, sig2,
        "signature with modified key must not match original signature"
    );
}

#[test]
fn hmac_sha256_sign_with_modified_message_fails_verification() {
    let key = "my-secure-key";
    let message1 = "audit-log-payload";
    let message2 = "audit-log-payload-modified"; // modified message

    let sig1 = hmac_sha256_sign(key, message1);
    let sig2 = hmac_sha256_sign(key, message2);

    assert_ne!(
        sig1, sig2,
        "signature of modified message must not match original signature"
    );
}

#[test]
fn scrypt_invalid_params_and_output_len() {
    assert!(scrypt_derive(b"pw", b"salt", 16, 0, 1, 64).is_err());
    assert!(scrypt_derive(b"pw", b"salt", 16, 8, 0, 64).is_err());
    assert!(scrypt_derive(b"pw", b"salt", 16, 8, 1, 0).is_err());
}

proptest! {
    #[test]
    fn hmac_always_emits_a_sha256_hex_digest(key in any::<String>(), message in any::<String>()) {
        let digest = hmac_sha256_sign(&key, &message);
        prop_assert_eq!(digest.len(), 64);
        prop_assert!(digest.bytes().all(|byte| byte.is_ascii_hexdigit()));
    }

    #[test]
    fn pbkdf2_output_size_is_exact(key_size in 0usize..=128) {
        let digest = pbkdf2_derive("property-password", "property-salt", 1, key_size);
        prop_assert_eq!(digest.len(), key_size * 2);
    }

    #[test]
    fn scrypt_rejects_non_power_of_two_cost(cost in 3u32..=1023u32) {
        prop_assume!(!cost.is_power_of_two());
        prop_assert!(scrypt_derive(b"password", b"salt", cost, 1, 1, 16).is_err());
    }
}
