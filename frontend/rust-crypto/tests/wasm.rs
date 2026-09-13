// Browser-parity KATs (testing session 9), run via `wasm-pack test --headless
// --chrome`. These prove the wasm build produces identical output to the native
// KAT suite in src/lib.rs (same RFC 7914 / RFC 4231 vectors) AND exercise the
// wasm-only error path where JsValue is real (scrypt_derive with r=0 → Err).
//
// Kept to the cheap vectors (c=1 PBKDF2, N=16 scrypt) so the headless run stays
// fast; the native suite already covers the heavier N=1024/16384 vectors.

#![cfg(target_arch = "wasm32")]

use uni_wasm_crypto::{hmac_sha256_sign, pbkdf2_derive, scrypt_derive};
use wasm_bindgen_test::*;

wasm_bindgen_test_configure!(run_in_browser);

#[wasm_bindgen_test]
fn pbkdf2_parity_rfc7914() {
    // RFC 7914 §11: P="passwd", S="salt", c=1, dkLen=64.
    assert_eq!(
        pbkdf2_derive("passwd", "salt", 1, 64).expect("valid PBKDF2 parameters"),
        "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc49ca9cccf179b645991664b39d77ef317c71b845b1e30bd509112041d3a19783" // pragma: allowlist secret
    );
}

#[wasm_bindgen_test]
fn hmac_parity_rfc4231_tc2() {
    // RFC 4231 §4.3 (TC2): key="Jefe", data="what do ya want for nothing?".
    assert_eq!(
        hmac_sha256_sign("Jefe", "what do ya want for nothing?"),
        "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843" // pragma: allowlist secret
    );
}

#[wasm_bindgen_test]
fn scrypt_parity_rfc7914_vector1() {
    // RFC 7914 §12 vector 1: P="" S="" N=16 r=1 p=1 dkLen=64.
    let out = scrypt_derive(b"", b"", 16, 1, 1, 64).expect("valid params");
    assert_eq!(
        hex::encode(out),
        "77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442fcd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906" // pragma: allowlist secret
    );
}

#[wasm_bindgen_test]
fn scrypt_invalid_r_returns_err() {
    // r=0 is rejected by ScryptParams::new → scrypt_derive maps to Err(JsValue).
    // This is the wasm-only path: JsValue construction would panic on native, so
    // it is exercised here in the browser where JsValue is real. (n=0 is NOT
    // tested — n.ilog2() panics before any param check.)
    assert!(scrypt_derive(b"pw", b"salt", 16, 0, 1, 64).is_err());
}
