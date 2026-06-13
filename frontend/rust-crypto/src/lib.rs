use wasm_bindgen::prelude::*;
use sha2::Sha256;
use hmac::{Hmac, Mac};
use pbkdf2::pbkdf2_hmac;
use scrypt::{scrypt, Params as ScryptParams};

type HmacSha256 = Hmac<Sha256>;

#[wasm_bindgen]
pub fn pbkdf2_derive(password: &str, salt: &str, iterations: u32, key_size: usize) -> String {
    let mut res = vec![0u8; key_size];
    pbkdf2_hmac::<Sha256>(password.as_bytes(), salt.as_bytes(), iterations, &mut res);
    hex::encode(res)
}

#[wasm_bindgen]
pub fn hmac_sha256_sign(key: &str, message: &str) -> String {
    let mut mac = HmacSha256::new_from_slice(key.as_bytes()).expect("HMAC can take key of any size");
    mac.update(message.as_bytes());
    let result = mac.finalize();
    hex::encode(result.into_bytes())
}

#[wasm_bindgen]
pub fn scrypt_derive(password: &[u8], salt: &[u8], n: u32, r: u32, p: u32, dk_len: usize) -> Result<Vec<u8>, JsValue> {
    let params = ScryptParams::new(n.ilog2() as u8, r, p, dk_len)
        .map_err(|e| JsValue::from_str(&format!("Invalid scrypt params: {:?}", e)))?;
    let mut res = vec![0u8; dk_len];
    scrypt(password, salt, &params, &mut res)
        .map_err(|e| JsValue::from_str(&format!("Scrypt failed: {:?}", e)))?;
    Ok(res)
}

// Native Known-Answer-Test (KAT) suite (testing session 9). The #[wasm_bindgen]
// functions are callable as plain Rust on a non-wasm target; PBKDF2/HMAC return
// hex Strings and scrypt returns Ok(Vec<u8>) on valid params (the JsValue error
// branch is never hit here — it lives only in the wasm-target error test in
// tests/wasm.rs, where JsValue is real). All vectors are canonical RFC values;
// running them against the RustCrypto reference impls (pbkdf2 0.12 / scrypt 0.11
// / hmac 0.12) is mutual confirmation: a PASS proves both the vector and the
// wiring. ⛔ No n=0 scrypt vector — n.ilog2() panics on zero.
#[cfg(all(test, not(target_arch = "wasm32")))]
mod tests {
    use super::*;

    // RFC 7914 §11: PBKDF2-HMAC-SHA-256, P="passwd", S="salt", c=1, dkLen=64.
    const PBKDF2_PASSWD_SALT_C1: &str = "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc49ca9cccf179b645991664b39d77ef317c71b845b1e30bd509112041d3a19783"; // pragma: allowlist secret

    // RFC 4231 §4.2 (TC1): key = 0x0b x20 (valid UTF-8: 0x0b is a control char),
    // data = "Hi There".
    const HMAC_TC1: &str = "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"; // pragma: allowlist secret
    // RFC 4231 §4.3 (TC2): key = "Jefe", data = "what do ya want for nothing?".
    const HMAC_TC2: &str = "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"; // pragma: allowlist secret

    // RFC 7914 §12: scrypt vectors (pass the actual N; scrypt_derive takes ilog2).
    const SCRYPT_V1: &str = "77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442fcd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906"; // pragma: allowlist secret
    const SCRYPT_V2: &str = "fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b3731622eaf30d92e22a3886ff109279d9830dac727afb94a83ee6d8360cbdfa2cc0640"; // pragma: allowlist secret
    const SCRYPT_V3: &str = "7023bdcb3afd7348461c06cd81fd38ebfda8fbba904f8e3ea9b543f6545da1f2d5432955613f0fcf62d49705242a9af9e61e85dc0d651e40dfcf017b45575887"; // pragma: allowlist secret

    #[test]
    fn pbkdf2_hmac_sha256_rfc7914_vector() {
        assert_eq!(pbkdf2_derive("passwd", "salt", 1, 64), PBKDF2_PASSWD_SALT_C1);
    }

    #[test]
    fn pbkdf2_length_tracks_key_size() {
        // dkLen=20 → 40 hex chars; sanity that key_size threads through.
        assert_eq!(pbkdf2_derive("pw", "salt", 2, 20).len(), 40);
    }

    #[test]
    fn hmac_sha256_rfc4231_tc1() {
        let key = "\u{0b}".repeat(20); // 0x0b x20 — a valid UTF-8 &str
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
        let out = scrypt_derive(b"pleaseletmein", b"SodiumChloride", 16384, 8, 1, 64)
            .expect("valid params");
        assert_eq!(hex::encode(out), SCRYPT_V3);
    }

    #[test]
    fn scrypt_dk_len_is_honored() {
        let out = scrypt_derive(b"pw", b"salt", 16, 1, 1, 32).expect("valid params");
        assert_eq!(out.len(), 32);
    }
}
